import copy
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import unittest
from unittest.mock import Mock, patch

import yaml

from core.errors import Cancelled, HubError
from core.installer import HubService
from core.security import URLPolicy
from core.storage import read_installed
from core.winget import MAX_DOWNLOAD, SOURCE_ID, SOURCE_TYPE, SOURCE_URL, WingetClient
from tests.helpers import TemporaryDirectory, Response, make_catalog, windows_executable


class WingetSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / "installed"
        self.cancel = threading.Event()
        self.progress, self.log = Mock(), Mock()
        self.manifest_url = "https://raw.githubusercontent.com/microsoft/winget-pkgs/" + "a" * 40 + "/manifests/o/Official/Emulator/1.0/Official.Emulator.installer.yaml"
        self.asset_url = "https://github.com/official/emulator/releases/download/v1.0/emulator.exe"
        self.body = windows_executable()
        self.policy = URLPolicy([
            "https://github.com/official/emulator",
            "https://raw.githubusercontent.com/microsoft/winget-pkgs", SOURCE_URL,
        ])
        self.client = WingetClient(self.policy)
        self.entry = {
            "id": "test-emulator", "emulator": "Testemulator", "exe": "emulator.exe",
            "winget_id": "Official.Emulator", "winget_version": "1.0", "winget_manifest_url": self.manifest_url,
        }
        self.manifest = {
            "PackageIdentifier": "Official.Emulator", "PackageVersion": "1.0",
            "ManifestType": "installer", "ManifestVersion": "1.6.0", "InstallerType": "portable", "Scope": "user",
            "Installers": [{"Architecture": "x64", "InstallerUrl": self.asset_url, "InstallerSha256": hashlib.sha256(self.body).hexdigest()}],
        }
        self.source = {"Name": "winget", "Arg": SOURCE_URL, "Type": SOURCE_TYPE, "Identifier": SOURCE_ID}

    def network(self, url, **kwargs):
        self.policy.validate(url)
        if url == self.manifest_url:
            return Response(yaml.safe_dump(self.manifest).encode())
        self.assertEqual(url, self.asset_url)
        return Response(self.body, headers={"Content-Length": str(len(self.body))})

    def runner(self, command, log, cancel_event):
        if command[1:4] == ["source", "export", "winget"]:
            return json.dumps(self.source)
        if command[1] == "install":
            self.target.mkdir()
            (self.target / "emulator.exe").write_bytes(windows_executable())
        return "Vorgang abgeschlossen\n"

    def install(self):
        with patch.object(self.policy, "get", side_effect=self.network), patch.object(self.client, "_executable", return_value="C:/winget.exe"), patch.object(self.client, "_run", side_effect=self.runner) as run:
            result = self.client.install(self.entry, self.target, self.progress, self.log, self.cancel)
            return result, run.call_args_list

    def test_install_pins_source_version_architecture_scope_and_returns_winget_record(self):
        record, calls = self.install()
        command = calls[-1].args[0]
        for flag, value in (
            ("--id", "Official.Emulator"), ("--version", "1.0"), ("--source", "winget"),
            ("--architecture", "x64"), ("--scope", "user"), ("--installer-type", "portable"),
            ("--location", str(self.target.absolute())),
        ):
            self.assertEqual(command[command.index(flag) + 1], value)
        for flag in ("--exact", "--accept-source-agreements", "--accept-package-agreements", "--disable-interactivity"):
            self.assertIn(flag, command)
        for forbidden in ("--force", "--ignore-security-hash", "--override", "--custom", "--skip-dependencies"):
            self.assertNotIn(forbidden, command)
        self.assertEqual(record["method"], "winget")
        self.assertFalse(record["managed"])
        self.assertEqual(record["winget_id"], "Official.Emulator")
        self.assertEqual(record["version"], "1.0")
        self.assertTrue(Path(record["exe_path"]).exists())
        self.assertEqual(record["shortcuts"], [])
        self.assertEqual(self.progress.call_args.args[0], 100)

    def test_manifest_requires_pinned_official_commit_and_explicit_matching_identity(self):
        for changes in (
            {"winget_manifest_url": self.manifest_url.replace("a" * 40, "master")},
            {"winget_manifest_url": self.manifest_url.replace("microsoft/winget-pkgs", "attacker/winget-pkgs")},
            {"winget_manifest_url": self.manifest_url + "?mutable=true"},
            {"winget_version": ""}, {"winget_id": "--force"}, {"winget_version": "1.0 --force"},
        ):
            entry = {**self.entry, **changes}
            with self.subTest(changes=changes), patch.object(self.policy, "get") as get, self.assertRaises(HubError):
                self.client._manifest(entry, self.cancel)
            get.assert_not_called()
        for changes in ({"PackageIdentifier": "Foreign.Emulator"}, {"PackageVersion": "2.0"}, {"ManifestType": "singleton"}):
            manifest = {**self.manifest, **changes}
            with self.subTest(changes=changes), patch.object(self.policy, "get", return_value=Response(yaml.safe_dump(manifest).encode())), self.assertRaises(HubError):
                self.client._manifest(self.entry, self.cancel)

    def test_manifest_rejects_admin_dependencies_custom_switches_and_unsafe_installer_types(self):
        for changes in (
            {"Scope": "machine"}, {"Scope": None}, {"InstallerType": "exe"}, {"InstallerType": "msi"},
            {"ElevationRequirement": "elevationRequired"}, {"InstallerSwitches": {"Silent": "/admin"}},
            {"Dependencies": {"PackageDependencies": [{"PackageIdentifier": "Other.Runtime"}]}},
            {"AppsAndFeaturesEntries": [{"DisplayName": "Other app"}]},
            {"UpgradeBehavior": "uninstallPrevious"}, {"InstallerSuccessCodes": [999]},
        ):
            manifest = {**self.manifest, **changes}
            with self.subTest(changes=changes), patch.object(self.policy, "get", return_value=Response(yaml.safe_dump(manifest).encode())), self.assertRaises(HubError):
                self.client._manifest(self.entry, self.cancel)

    def test_manifest_rejects_missing_ambiguous_x64_and_unapproved_other_architecture_download(self):
        original = self.manifest["Installers"][0]
        for installers in (
            [], [{**original, "Architecture": "arm64"}], [original, dict(original)],
            [original, {**original, "Architecture": "x86", "InstallerUrl": "https://unofficial.example/emulator.exe"}],
            [{**original, "InstallerSha256": "not-a-hash"}],
            [{**original, "InstallerUrl": self.asset_url.replace("/v1.0/", "/latest/")}],
        ):
            manifest = {**self.manifest, "Installers": installers}
            with self.subTest(installers=installers), patch.object(self.policy, "get", return_value=Response(yaml.safe_dump(manifest).encode())), self.assertRaises(HubError):
                self.client._manifest(self.entry, self.cancel)

    def test_manifest_rejects_duplicate_yaml_fields_and_recursive_aliases(self):
        for raw in (
            yaml.safe_dump(self.manifest) + "Scope: machine\n",
            "self: &self {again: *self}\n",
        ):
            with self.subTest(raw=raw), patch.object(self.policy, "get", return_value=Response(raw.encode())), self.assertRaises(HubError):
                self.client._manifest(self.entry, self.cancel)

    def test_manifest_and_microsoft_source_must_also_be_explicitly_whitelisted(self):
        client = WingetClient(URLPolicy(["https://github.com/official/emulator"]))
        with patch.object(client.policy, "get") as get, self.assertRaises(HubError):
            client._manifest(self.entry, self.cancel)
        get.assert_not_called()
        with patch.object(client, "_run") as run, self.assertRaises(HubError):
            client._verify_source("winget.exe", self.log, self.cancel)
        run.assert_not_called()

    def test_zip_manifest_requires_safe_single_nested_portable_executable(self):
        manifest = copy.deepcopy(self.manifest)
        manifest.update({"InstallerType": "zip", "NestedInstallerType": "portable", "NestedInstallerFiles": [{"RelativeFilePath": "app/emulator.exe"}]})
        manifest["Installers"][0]["InstallerUrl"] = self.asset_url.removesuffix(".exe") + ".zip"
        with patch.object(self.policy, "get", return_value=Response(yaml.safe_dump(manifest).encode())):
            self.assertEqual(self.client._manifest(self.entry, self.cancel)["InstallerType"], "zip")
        for changes in (
            {"NestedInstallerType": "exe"}, {"NestedInstallerFiles": [{"RelativeFilePath": "../external.exe"}]},
            {"NestedInstallerFiles": [{"RelativeFilePath": "program.exe:stream"}]},
            {"NestedInstallerFiles": [{"RelativeFilePath": "emulator.exe", "PortableCommandAlias": "../external"}]},
            {"NestedInstallerFiles": [{"RelativeFilePath": "first.exe"}, {"RelativeFilePath": "second.exe"}]},
        ):
            unsafe = {**manifest, **changes}
            with self.subTest(changes=changes), patch.object(self.policy, "get", return_value=Response(yaml.safe_dump(unsafe).encode())), self.assertRaises(HubError):
                self.client._manifest(self.entry, self.cancel)

    def test_source_export_must_match_all_official_microsoft_source_fields(self):
        for changes in (
            {"Arg": "http://cdn.winget.microsoft.com/cache"}, {"Arg": "https://unofficial.example/cache"},
            {"Type": "Microsoft.Rest"}, {"Identifier": "Foreign.Source"}, {"Name": "msstore"},
        ):
            source = {**self.source, **changes}
            with self.subTest(changes=changes), patch.object(self.client, "_run", return_value=json.dumps(source)), self.assertRaises(HubError):
                self.client._verify_source("winget.exe", self.log, self.cancel)
        for raw in ("not JSON", "[]", "{}"):
            with self.subTest(raw=raw), patch.object(self.client, "_run", return_value=raw), self.assertRaises(HubError):
                self.client._verify_source("winget.exe", self.log, self.cancel)

    def test_hash_mismatch_stops_before_winget_install_process(self):
        self.manifest["Installers"][0]["InstallerSha256"] = "0" * 64
        with patch.object(self.policy, "get", side_effect=self.network), patch.object(self.client, "_executable", return_value="winget.exe"), patch.object(self.client, "_run", return_value=json.dumps(self.source)) as run, self.assertRaises(HubError):
            self.client.install(self.entry, self.target, self.progress, self.log, self.cancel)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][1], "source")
        self.assertFalse(self.target.exists())

    def test_preflight_rejects_truncated_and_oversized_responses(self):
        installer = {"InstallerUrl": self.asset_url, "InstallerSha256": hashlib.sha256(self.body).hexdigest()}
        for body, total in ((self.body[:-1], len(self.body)), (self.body, MAX_DOWNLOAD + 1)):
            with self.subTest(total=total), patch.object(self.policy, "get", return_value=Response(body, headers={"Content-Length": str(total)})), self.assertRaises(HubError):
                self.client._preflight(installer, self.progress, self.cancel)

    def test_successful_winget_without_target_executable_requests_manual_registration(self):
        with patch.object(self.policy, "get", side_effect=self.network), patch.object(self.client, "_executable", return_value="winget.exe"), patch.object(self.client, "_run", return_value=json.dumps(self.source)):
            with self.assertRaisesRegex(HubError, "manuell zuordnen"):
                self.client.install(self.entry, self.target, self.progress, self.log, self.cancel)

    def test_uninstall_is_exact_user_scope_and_never_removes_a_directory_itself(self):
        self.target.mkdir()
        personal = self.target / "personal.txt"
        personal.write_text("keep", encoding="utf-8")
        record = {"method": "winget", "winget_id": "Official.Emulator", "version": "1.0", "managed": False, "path": str(self.target)}
        with patch.object(self.client, "_executable", return_value="winget.exe"), patch.object(self.client, "_run", return_value=json.dumps(self.source)) as run:
            self.client.uninstall(record, self.log, self.cancel)
        command = run.call_args.args[0]
        self.assertEqual(command[1], "uninstall")
        self.assertEqual(command[command.index("--id") + 1], "Official.Emulator")
        self.assertEqual(command[command.index("--version") + 1], "1.0")
        self.assertEqual(command[command.index("--scope") + 1], "user")
        self.assertIn("--exact", command)
        self.assertNotIn("--purge", command)
        self.assertEqual(personal.read_text(encoding="utf-8"), "keep")

    def test_cancellation_before_work_never_starts_subprocess_or_network(self):
        self.cancel.set()
        with patch.object(self.policy, "get") as get, patch("core.winget.subprocess.Popen") as spawn:
            with self.assertRaises(Cancelled):
                self.client.install(self.entry, self.target, self.progress, self.log, self.cancel)
            with self.assertRaises(Cancelled):
                self.client.uninstall({"method": "winget"}, self.log, self.cancel)
            with self.assertRaises(Cancelled):
                self.client._run(["winget.exe", "install"], self.log, self.cancel)
        get.assert_not_called()
        spawn.assert_not_called()

    def test_running_process_finishes_safely_after_cancel_and_logs_file_output(self):
        process = Mock(returncode=0)

        def spawn(command, **kwargs):
            writer = kwargs["stdout"]
            state = [0]

            def communicate(timeout):
                self.assertEqual(timeout, 1)
                state[0] += 1
                if state[0] == 1:
                    writer.write(b"running\n")
                    writer.flush()
                    self.cancel.set()
                    raise subprocess.TimeoutExpired(command, timeout)
                writer.write(b"completed\n")
                writer.flush()
                return None, None

            process.communicate.side_effect = communicate
            return process

        with patch("core.winget.subprocess.Popen", side_effect=spawn) as start:
            output = self.client._run(["winget.exe", "install"], self.log, self.cancel)
        self.assertEqual(output, "running\ncompleted\n")
        self.assertEqual(process.communicate.call_count, 2)
        process.kill.assert_not_called()
        process.terminate.assert_not_called()
        self.assertFalse(start.call_args.kwargs["shell"])
        self.assertTrue(any("Abbruch angefordert" in str(call) for call in self.log.call_args_list))

    def test_missing_winget_reports_manual_fallback_without_installer_process(self):
        with patch("core.winget.shutil.which", return_value=None), self.assertRaisesRegex(HubError, "manuelle Anleitung"):
            self.client._executable()


class WingetServiceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.catalog, _ = make_catalog(self.root)
        self.entry = self.catalog.items[0]
        self.entry.update({
            "install_methode": "winget", "winget_id": "Official.Emulator", "winget_version": "1.0",
            "winget_manifest_url": "https://raw.githubusercontent.com/microsoft/winget-pkgs/" + "a" * 40 + "/manifests/o/Official/Emulator/1.0/Official.Emulator.installer.yaml",
        })
        self.catalog.official_sources.extend(["https://raw.githubusercontent.com/microsoft/winget-pkgs", SOURCE_URL])
        self.service = HubService(self.catalog, self.root / "data")
        self.addCleanup(self.close_logger)
        self.progress, self.log = Mock(), Mock()
        self.cancel = threading.Event()

    def close_logger(self):
        for handler in list(self.service.logger.handlers):
            handler.close()
            self.service.logger.removeHandler(handler)

    def backend_install(self, entry, target, progress, log, cancel_event):
        target.mkdir(parents=True, exist_ok=True)
        start = target / "emulator.exe"
        start.write_bytes(windows_executable())
        return {
            "path": str(target), "exe_path": str(start), "version": "1.0", "date": "2026-10-01",
            "managed": False, "method": "winget", "winget_id": "Official.Emulator", "shortcuts": [],
        }

    def install(self):
        with patch.object(self.service.winget, "install", side_effect=self.backend_install) as install:
            record = self.service.install(self.entry, self.progress, self.log, self.cancel)
        install.assert_called_once()
        self.assertEqual(install.call_args.args[1], self.service.emulator_dir / self.entry["id"])
        return record

    def test_service_persists_winget_record_and_delegates_package_uninstall_before_removing_registration(self):
        record = self.install()
        self.assertFalse(record["managed"])
        self.assertEqual(read_installed(self.service.installed_path), self.service.installed)
        self.assertTrue(self.service.is_installed(self.entry["id"]))
        with patch.object(self.service.winget, "uninstall") as uninstall, patch("core.installer.remove_managed_tree") as remove:
            self.service.uninstall(self.entry, self.log, self.cancel)
        uninstall.assert_called_once()
        self.assertEqual(uninstall.call_args.args[0], record)
        remove.assert_not_called()
        self.assertEqual(read_installed(self.service.installed_path), {})
        self.assertEqual(self.service.installed, {})

    def test_failed_winget_uninstall_keeps_registration_and_package_folder(self):
        record = self.install()
        original = self.service.installed_path.read_bytes()
        with patch.object(self.service.winget, "uninstall", side_effect=HubError("WinGet fehlgeschlagen")), self.assertRaises(HubError):
            self.service.uninstall(self.entry, self.log, self.cancel)
        self.assertEqual(self.service.installed_path.read_bytes(), original)
        self.assertTrue(Path(record["exe_path"]).exists())
        self.assertTrue(self.service.is_installed(self.entry["id"]))

    def test_failed_registration_save_reports_manual_recovery_and_keeps_installed_files(self):
        with patch.object(self.service.winget, "install", side_effect=self.backend_install), patch.object(self.service, "_save", side_effect=HubError("disk locked")):
            with self.assertRaisesRegex(HubError, "Anleitung"):
                self.service.install(self.entry, self.progress, self.log, self.cancel)
        self.assertEqual(self.service.installed, {})
        self.assertTrue((self.service.emulator_dir / self.entry["id"] / "emulator.exe").exists())

    def test_winget_record_cannot_be_replaced_by_manual_registration(self):
        record = self.install()
        own_folder = self.root / "another-folder"
        own_folder.mkdir()
        (own_folder / "emulator.exe").write_bytes(windows_executable())
        with self.assertRaises(HubError):
            self.service.register_manual(self.entry, own_folder)
        self.assertEqual(self.service.installed[self.entry["id"]], record)
        self.assertTrue((own_folder / "emulator.exe").exists())

    def test_existing_manual_registration_blocks_winget_before_package_operation(self):
        own_folder = self.root / "personal"
        own_folder.mkdir()
        (own_folder / "emulator.exe").write_bytes(windows_executable())
        self.service.register_manual(self.entry, own_folder)
        with patch.object(self.service.winget, "install") as install, self.assertRaises(HubError):
            self.service.install(self.entry, self.progress, self.log, self.cancel)
        install.assert_not_called()
        self.assertTrue((own_folder / "emulator.exe").exists())

    def test_updates_use_only_reviewed_winget_catalog_version(self):
        self.install()
        self.entry["winget_version"] = "2.0"
        with patch.object(self.service.github, "latest") as github:
            result = self.service.check_updates(self.progress, self.log, self.cancel)
        github.assert_not_called()
        self.assertEqual(result, {self.entry["id"]: "2.0"})
        self.assertEqual(self.service.status(self.entry["id"]), "Update verfügbar")


if __name__ == "__main__":
    unittest.main()
