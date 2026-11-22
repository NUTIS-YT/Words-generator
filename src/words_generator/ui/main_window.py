from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from words_generator.api.client import APIConfig
from words_generator.models.project import ProjectSettings
from words_generator.storage.app_config import AppConfigStore, CredentialStore
from words_generator.storage.project_store import ProjectError, ProjectStore
from words_generator.ui.pages import HistoryPage, ProjectPage, SettingsPage, StatisticsPage
from words_generator.workers.api_test_worker import ApiTestWorker
from words_generator.workers.generation_worker import GenerationWorker


APP_STYLE = """
QMainWindow, QWidget { background: #17191d; color: #e7e9ed; font-size: 13px; }
QLabel#pageTitle { font-size: 26px; font-weight: 650; color: #f2f4f7; }
QLabel#pageSubtitle, QLabel#mutedLabel { color: #a4aab4; }
QLabel#sectionTitle { font-size: 18px; font-weight: 600; }
QLabel#metricValue { font-size: 22px; font-weight: 650; color: #f3f5f7; }
QFrame#metricCard, QGroupBox { background: #202329; border: 1px solid #343941; border-radius: 10px; }
QGroupBox { margin-top: 10px; padding: 14px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QListWidget {
    background: #111317; border: 1px solid #3a4049; border-radius: 7px; padding: 8px; selection-background-color: #526b8d;
}
QComboBox::drop-down { border: 0; width: 22px; }
QPushButton { background: #303640; border: 1px solid #414955; border-radius: 7px; padding: 9px 13px; }
QPushButton:hover { background: #3b4450; }
QPushButton:disabled { color: #737985; background: #24282e; }
QPushButton#primaryButton { background: #45668f; border-color: #587ba7; color: white; font-weight: 600; }
QPushButton#primaryButton:hover { background: #5277a4; }
QProgressBar { background: #272c33; border: 0; border-radius: 5px; height: 12px; text-align: center; }
QProgressBar::chunk { background: #6a91bd; border-radius: 5px; }
QListWidget#navigation { background: #131519; border: 0; padding: 10px; }
QListWidget#navigation::item { padding: 13px 12px; border-radius: 7px; margin: 3px 0; }
QListWidget#navigation::item:selected { background: #303d4e; color: #ffffff; }
QStatusBar { background: #131519; color: #a4aab4; }
"""


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Words Generator")
        self.resize(1180, 780)
        self.setMinimumSize(900, 620)
        self.setStyleSheet(APP_STYLE)

        self.config_store = AppConfigStore()
        self.config = self.config_store.load()
        self.credentials = CredentialStore()
        self.project: ProjectStore | None = None
        self.worker: GenerationWorker | None = None
        self.test_worker: ApiTestWorker | None = None
        self._api_key_memory = self.credentials.get_api_key()

        self._build_menu()
        container = QWidget()
        outer = QHBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QWidget()
        sidebar.setFixedWidth(205)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 20, 12, 12)
        brand = QLabel("WORDS\nGENERATOR")
        brand.setStyleSheet("font-size: 17px; font-weight: 750; letter-spacing: 1px; padding: 8px 10px 18px;")
        sidebar_layout.addWidget(brand)
        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.addItems(["Project", "Settings", "Statistics", "History"])
        self.navigation.setCurrentRow(0)
        sidebar_layout.addWidget(self.navigation, 1)
        version = QLabel("Version 0.1.0")
        version.setObjectName("mutedLabel")
        version.setContentsMargins(10, 6, 10, 4)
        sidebar_layout.addWidget(version)
        outer.addWidget(sidebar)

        self.stack = QStackedWidget()
        self.project_page = ProjectPage()
        self.settings_page = SettingsPage()
        self.statistics_page = StatisticsPage()
        self.history_page = HistoryPage()
        for page in (self.project_page, self.settings_page, self.statistics_page, self.history_page):
            self.stack.addWidget(page)
        outer.addWidget(self.stack, 1)
        self.setCentralWidget(container)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready · No project opened")

        self.navigation.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.project_page.create_requested.connect(self.create_project)
        self.project_page.open_requested.connect(self.open_project)
        self.project_page.start_requested.connect(self.start_generation)
        self.project_page.pause_requested.connect(self.pause_generation)
        self.project_page.resume_requested.connect(self.resume_generation)
        self.project_page.stop_requested.connect(self.stop_generation)
        self.settings_page.save_requested.connect(self.save_settings)
        self.settings_page.test_requested.connect(self.test_connection)
        self.settings_page.set_app_config(self.config, self._api_key_memory)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        new_action = QAction("New project…", self)
        new_action.triggered.connect(self.create_project)
        open_action = QAction("Open project…", self)
        open_action.triggered.connect(self.open_project)
        save_action = QAction("Save settings", self)
        save_action.triggered.connect(self.save_settings)
        file_menu.addAction(new_action)
        file_menu.addAction(open_action)
        file_menu.addSeparator()
        file_menu.addAction(save_action)

    def _set_project(self, store: ProjectStore) -> None:
        self.project = store
        self.project_page.set_project(store)
        self.settings_page.set_project_settings(store.settings)
        self.history_page.set_project(store)
        self.statusBar().showMessage(f"Project opened · {store.path}")
        recent = [item for item in self.config.recent_projects if item != str(store.path)]
        self.config.recent_projects = [str(store.path), *recent][:10]
        self.config_store.save(self.config)

    def create_project(self) -> None:
        parent = QFileDialog.getExistingDirectory(self, "Choose a parent directory for the project")
        if not parent:
            return
        name, accepted = QInputDialog.getText(self, "New project", "Project name:")
        if not accepted:
            return
        name = name.strip()
        if not name or name in {".", ".."} or "/" in name or "\\" in name:
            QMessageBox.warning(self, "Invalid name", "Enter a project name without path separators.")
            return
        try:
            settings = ProjectSettings(name=name)
            store = ProjectStore.create(Path(parent) / name, settings)
            self._set_project(store)
        except (ProjectError, OSError, ValueError) as exc:
            QMessageBox.critical(self, "Could not create project", str(exc))

    def open_project(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Open Words Generator project")
        if not directory:
            return
        try:
            store = ProjectStore.open(directory)
            self._set_project(store)
        except (ProjectError, OSError, ValueError) as exc:
            QMessageBox.critical(self, "Could not open project", str(exc))

    def save_settings(self) -> None:
        try:
            sampling = self.settings_page.get_sampling()
            self.config.api_base_url = self.settings_page.base_url.text().strip()
            self.config.model = self.settings_page.model.currentText().strip()
            self.config.timeout_seconds = self.settings_page.timeout.value()
            self.config.sampling = sampling
            api_key = self.settings_page.api_key.text().strip()
            stored = self.credentials.set_api_key(api_key)
            self._api_key_memory = api_key
            self.config_store.save(self.config)
            if self.project is not None:
                project_settings = self.settings_page.get_project_settings(self.project.settings)
                project_settings.target_words = self.project_page.target_words.value()
                self.project.update_settings(project_settings)
                self.project_page.set_project(self.project)
            if api_key and not stored:
                QMessageBox.warning(
                    self,
                    "Credential storage unavailable",
                    "The API key is available for this app session but could not be saved to the system credential store. It was not written to a file.",
                )
            self.statusBar().showMessage("Settings saved", 4000)
        except (ValueError, ProjectError, OSError) as exc:
            QMessageBox.warning(self, "Invalid settings", str(exc))

    def _api_config_from_ui(self) -> APIConfig:
        return APIConfig(
            base_url=self.settings_page.base_url.text().strip(),
            model=self.settings_page.model.currentText().strip(),
            api_key=self.settings_page.api_key.text().strip() or self._api_key_memory,
            timeout_seconds=self.settings_page.timeout.value(),
        )

    def test_connection(self) -> None:
        if self.test_worker is not None and self.test_worker.isRunning():
            return
        try:
            api_config = self._api_config_from_ui()
            api_config.validate()
        except ValueError as exc:
            QMessageBox.warning(self, "Check API settings", str(exc))
            return
        self.settings_page.test_button.setEnabled(False)
        self.settings_page.test_button.setText("Connecting…")
        self.test_worker = ApiTestWorker(api_config)
        self.test_worker.completed.connect(self._connection_test_succeeded)
        self.test_worker.failed.connect(self._connection_test_failed)
        self.test_worker.finished.connect(self._connection_test_finished)
        self.test_worker.start()

    def _connection_test_succeeded(self, models: list[str]) -> None:
        current = self.settings_page.model.currentText()
        self.settings_page.model.clear()
        self.settings_page.model.addItems(models)
        self.settings_page.model.setCurrentText(current)
        QMessageBox.information(
            self,
            "Connection successful",
            f"The API responded successfully. Found {len(models)} model(s).",
        )

    def _connection_test_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Connection failed", message)

    def _connection_test_finished(self) -> None:
        self.settings_page.test_button.setEnabled(True)
        self.settings_page.test_button.setText("Test connection / load models")
        self.test_worker = None

    def start_generation(self, target: int) -> None:
        if self.project is None:
            QMessageBox.information(self, "No project", "Create or open a project first.")
            return
        if self.worker is not None and self.worker.isRunning():
            return
        try:
            api_config = self._api_config_from_ui()
            api_config.validate(require_model=True)
            project_settings = self.settings_page.get_project_settings(self.project.settings)
            project_settings.target_words = target
            project_settings.sampling = self.settings_page.get_sampling()
            project_settings.validate()
            self.project.update_settings(project_settings)
            sampling = self.settings_page.get_sampling()
        except (ValueError, ProjectError) as exc:
            QMessageBox.warning(self, "Cannot start generation", str(exc))
            return

        self.statistics_page.log.clear()
        self.statistics_page.progress.setValue(0)
        self.project_page.set_running(True)
        self.statusBar().showMessage("Generation started…")
        self.worker = GenerationWorker(self.project, project_settings, api_config, sampling)
        self.worker.stats_updated.connect(self.statistics_page.update_stats)
        self.worker.event_logged.connect(self.statistics_page.add_event)
        self.worker.generation_finished.connect(self._generation_finished)
        self.worker.worker_error.connect(self._worker_error)
        self.worker.finished.connect(self._worker_thread_finished)
        self.worker.start()
        self.navigation.setCurrentRow(2)

    def pause_generation(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.request_pause()
            self.project_page.set_paused(True)
            self.statusBar().showMessage("Pause requested; current request will finish first.")

    def resume_generation(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.request_resume()
            self.project_page.set_paused(False)
            self.statusBar().showMessage("Generation resumed.")

    def stop_generation(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.request_stop()
            self.statusBar().showMessage("Stopping after the current request…")

    def _generation_finished(self, result: dict[str, object]) -> None:
        status = str(result.get("status", "finished"))
        added = int(result.get("added", 0))
        self.statusBar().showMessage(f"Generation {status} · {added:,} word(s) added", 8000)
        if self.project is not None:
            self.project_page.word_count.setText(f"{self.project.word_count:,} unique words in words.txt")
            self.history_page.set_project(self.project)

    def _worker_error(self, message: str) -> None:
        self.statusBar().showMessage("Generation failed", 8000)
        QMessageBox.critical(self, "Generation error", message)

    def _worker_thread_finished(self) -> None:
        self.project_page.set_running(False)
        if self.project is not None:
            self.project_page.word_count.setText(f"{self.project.word_count:,} unique words in words.txt")
            self.history_page.set_project(self.project)
        worker = self.worker
        self.worker = None
        if worker is not None:
            worker.deleteLater()

    def closeEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        if self.worker is not None and self.worker.isRunning():
            answer = QMessageBox.question(
                self,
                "Generation is running",
                "Stop the current generation and close the application?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.worker.request_stop()
            if not self.worker.wait(5000):
                QMessageBox.warning(
                    self,
                    "Generation is stopping",
                    "The active request has not finished yet. Close the application after it stops.",
                )
                event.ignore()
                return
        event.accept()
