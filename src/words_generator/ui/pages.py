from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from words_generator.core.prompts import PROMPT_TEMPLATES, prompt_for_template
from words_generator.models.project import ProjectSettings
from words_generator.models.sampling import SamplingSettings
from words_generator.storage.app_config import AppConfig
from words_generator.storage.project_store import ProjectStore


class Page(QWidget):
    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__()
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(28, 24, 28, 24)
        self.root.setSpacing(16)
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        self.root.addWidget(heading)
        if subtitle:
            description = QLabel(subtitle)
            description.setObjectName("pageSubtitle")
            description.setWordWrap(True)
            self.root.addWidget(description)


def _card(title: str, description: str = "") -> tuple[QGroupBox, QVBoxLayout]:
    box = QGroupBox(title)
    layout = QVBoxLayout(box)
    if description:
        label = QLabel(description)
        label.setObjectName("mutedLabel")
        label.setWordWrap(True)
        layout.addWidget(label)
    return box, layout


class ProjectPage(Page):
    create_requested = Signal()
    open_requested = Signal()
    start_requested = Signal(int)
    pause_requested = Signal()
    resume_requested = Signal()
    stop_requested = Signal()

    def __init__(self) -> None:
        super().__init__("Project", "Create a workspace or open an existing word collection.")

        actions = QHBoxLayout()
        self.create_button = QPushButton("New project")
        self.create_button.setObjectName("primaryButton")
        self.open_button = QPushButton("Open project")
        self.create_button.clicked.connect(self.create_requested.emit)
        self.open_button.clicked.connect(self.open_requested.emit)
        actions.addWidget(self.create_button)
        actions.addWidget(self.open_button)
        actions.addStretch(1)
        self.root.addLayout(actions)

        self.project_name = QLabel("No project opened")
        self.project_name.setObjectName("sectionTitle")
        self.project_path = QLabel("Create a new project or open an existing project directory.")
        self.project_path.setObjectName("mutedLabel")
        self.project_path.setWordWrap(True)
        self.word_count = QLabel("0 words in words.txt")
        project_card, project_layout = _card("Current workspace")
        project_layout.addWidget(self.project_name)
        project_layout.addWidget(self.project_path)
        project_layout.addWidget(self.word_count)
        self.root.addWidget(project_card)

        generation_card, generation_layout = _card(
            "Generation target",
            "The target is the number of new unique words to add during the next run.",
        )
        form = QFormLayout()
        self.target_words = QSpinBox()
        self.target_words.setRange(1, 1_000_000)
        self.target_words.setValue(100)
        form.addRow("New words to generate", self.target_words)
        generation_layout.addLayout(form)
        self.start_button = QPushButton("Start generation")
        self.start_button.setObjectName("primaryButton")
        self.pause_button = QPushButton("Pause")
        self.resume_button = QPushButton("Resume")
        self.stop_button = QPushButton("Stop")
        self.pause_button.setEnabled(False)
        self.resume_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        controls = QHBoxLayout()
        for button in (self.start_button, self.pause_button, self.resume_button, self.stop_button):
            controls.addWidget(button)
        generation_layout.addLayout(controls)
        self.root.addWidget(generation_card)
        self.root.addStretch(1)

        self.start_button.clicked.connect(lambda: self.start_requested.emit(self.target_words.value()))
        self.pause_button.clicked.connect(self.pause_requested.emit)
        self.resume_button.clicked.connect(self.resume_requested.emit)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.set_project(None)

    def set_project(self, store: ProjectStore | None) -> None:
        self._store = store
        enabled = store is not None
        self.start_button.setEnabled(enabled)
        if store is None:
            self.project_name.setText("No project opened")
            self.project_path.setText("Create a new project or open an existing project directory.")
            self.word_count.setText("0 words in words.txt")
            return
        self.project_name.setText(store.settings.name)
        self.project_path.setText(str(store.path))
        self.word_count.setText(f"{store.word_count:,} unique words in words.txt")
        self.target_words.setValue(store.settings.target_words)

    def set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running and self._store is not None)
        self.pause_button.setEnabled(running)
        self.resume_button.setEnabled(False)
        self.stop_button.setEnabled(running)
        self.create_button.setEnabled(not running)
        self.open_button.setEnabled(not running)

    def set_paused(self, paused: bool) -> None:
        self.pause_button.setEnabled(not paused)
        self.resume_button.setEnabled(paused)


class SettingsPage(Page):
    save_requested = Signal()
    test_requested = Signal()

    def __init__(self) -> None:
        super().__init__("Settings", "Configure the model endpoint, vocabulary target and sampling parameters.")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(14)

        api_card, api_layout = _card(
            "OpenAI Compatible API",
            "Use the API root or a URL ending in /v1. Credentials are stored separately from project files.",
        )
        api_form = QFormLayout()
        self.base_url = QLineEdit("http://localhost:8080/v1")
        self.base_url.setPlaceholderText("https://your-server.example/v1")
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("API key (optional for local servers)")
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.model.setPlaceholderText("Select or enter a model identifier")
        self.timeout = QDoubleSpinBox()
        self.timeout.setRange(1, 600)
        self.timeout.setDecimals(1)
        self.timeout.setSuffix(" s")
        self.timeout.setValue(60)
        api_form.addRow("Base URL", self.base_url)
        api_form.addRow("API Key", self.api_key)
        api_form.addRow("Model", self.model)
        api_form.addRow("Request timeout", self.timeout)
        api_layout.addLayout(api_form)
        api_buttons = QHBoxLayout()
        self.test_button = QPushButton("Test connection / load models")
        self.test_button.clicked.connect(self.test_requested.emit)
        api_buttons.addWidget(self.test_button)
        api_buttons.addStretch(1)
        api_layout.addLayout(api_buttons)
        content_layout.addWidget(api_card)

        vocabulary_card, vocabulary_layout = _card(
            "Vocabulary rules",
            "Preset buttons fill the editable system prompt. Your own changes are preserved until you explicitly choose another preset.",
        )
        vocabulary_form = QFormLayout()
        self.language = QComboBox()
        self.language.setEditable(True)
        self.language.addItems(["English", "Russian", "German", "French", "Spanish", "Dutch", "Italian", "Japanese", "Chinese"])
        self.part_of_speech = QComboBox()
        self.part_of_speech.setEditable(True)
        self.part_of_speech.addItems(["Nouns", "Verbs", "Adjectives", "Adverbs", "Pronouns", "Numerals"])
        vocabulary_form.addRow("Language", self.language)
        vocabulary_form.addRow("Part of speech", self.part_of_speech)
        vocabulary_layout.addLayout(vocabulary_form)
        preset_row = QHBoxLayout()
        for template_id, (label, _) in PROMPT_TEMPLATES.items():
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, key=template_id: self.apply_template(key))
            preset_row.addWidget(button)
        vocabulary_layout.addLayout(preset_row)
        self.prompt = QPlainTextEdit()
        self.prompt.setMinimumHeight(150)
        self.prompt.setPlainText(ProjectSettings().system_prompt)
        vocabulary_layout.addWidget(self.prompt)
        prompt_actions = QHBoxLayout()
        self.build_prompt_button = QPushButton("Build prompt from current rules")
        self.build_prompt_button.clicked.connect(self.build_prompt_from_rules)
        prompt_actions.addWidget(self.build_prompt_button)
        prompt_actions.addStretch(1)
        vocabulary_layout.addLayout(prompt_actions)
        content_layout.addWidget(vocabulary_card)

        sampling_card, sampling_layout = _card(
            "Sampling parameters",
            "Starting values are a practical baseline, not universally optimal settings for every model.",
        )
        sampling_form = QFormLayout()
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0, 2)
        self.temperature.setSingleStep(0.05)
        self.temperature.setValue(0.9)
        self.top_p = QDoubleSpinBox()
        self.top_p.setRange(0.01, 1)
        self.top_p.setSingleStep(0.05)
        self.top_p.setValue(0.95)
        self.frequency_penalty = QDoubleSpinBox()
        self.frequency_penalty.setRange(-2, 2)
        self.frequency_penalty.setSingleStep(0.1)
        self.presence_penalty = QDoubleSpinBox()
        self.presence_penalty.setRange(-2, 2)
        self.presence_penalty.setSingleStep(0.1)
        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(1, 4096)
        self.max_tokens.setValue(24)
        sampling_form.addRow("Temperature", self.temperature)
        sampling_form.addRow("Top P", self.top_p)
        sampling_form.addRow("Frequency penalty", self.frequency_penalty)
        sampling_form.addRow("Presence penalty", self.presence_penalty)
        sampling_form.addRow("Max tokens", self.max_tokens)
        sampling_layout.addLayout(sampling_form)
        defaults_button = QPushButton("Reset sampler defaults")
        defaults_button.clicked.connect(self.reset_sampling)
        sampling_layout.addWidget(defaults_button, alignment=Qt.AlignmentFlag.AlignLeft)
        content_layout.addWidget(sampling_card)
        content_layout.addStretch(1)
        scroll.setWidget(content)
        self.root.addWidget(scroll, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self.save_button = QPushButton("Save settings")
        self.save_button.setObjectName("primaryButton")
        self.save_button.clicked.connect(self.save_requested.emit)
        footer.addWidget(self.save_button)
        self.root.addLayout(footer)
        self._template_id = "standard"

    def apply_template(self, template_id: str) -> None:
        self.prompt.setPlainText(
            prompt_for_template(template_id, self.language.currentText(), self.part_of_speech.currentText())
        )
        self._template_id = template_id

    def build_prompt_from_rules(self) -> None:
        base = prompt_for_template("standard", self.language.currentText(), self.part_of_speech.currentText())
        language = self.language.currentText().strip() or "the selected language"
        part_of_speech = self.part_of_speech.currentText().strip() or "the selected part of speech"
        self.prompt.setPlainText(
            f"{base}\n\nGeneration constraints:\n- Language: {language}\n- Part of speech: {part_of_speech}"
        )
        self._template_id = "standard"

    def reset_sampling(self) -> None:
        defaults = SamplingSettings()
        self.temperature.setValue(defaults.temperature)
        self.top_p.setValue(defaults.top_p)
        self.frequency_penalty.setValue(defaults.frequency_penalty)
        self.presence_penalty.setValue(defaults.presence_penalty)
        self.max_tokens.setValue(defaults.max_tokens)

    def set_app_config(self, config: AppConfig, api_key: str) -> None:
        self.base_url.setText(config.api_base_url)
        self.model.setCurrentText(config.model)
        self.timeout.setValue(config.timeout_seconds)
        self.api_key.setText(api_key)
        self.set_sampling(config.sampling)

    def set_sampling(self, sampling: SamplingSettings) -> None:
        self.temperature.setValue(sampling.temperature)
        self.top_p.setValue(sampling.top_p)
        self.frequency_penalty.setValue(sampling.frequency_penalty)
        self.presence_penalty.setValue(sampling.presence_penalty)
        self.max_tokens.setValue(sampling.max_tokens)

    def get_sampling(self) -> SamplingSettings:
        result = SamplingSettings(
            temperature=self.temperature.value(),
            top_p=self.top_p.value(),
            frequency_penalty=self.frequency_penalty.value(),
            presence_penalty=self.presence_penalty.value(),
            max_tokens=self.max_tokens.value(),
        )
        result.validate()
        return result

    def set_project_settings(self, settings: ProjectSettings) -> None:
        self.language.setCurrentText(settings.language)
        self.part_of_speech.setCurrentText(settings.part_of_speech)
        self.prompt.setPlainText(settings.system_prompt)
        self._template_id = settings.prompt_template
        self.set_sampling(settings.sampling)

    def get_project_settings(self, current: ProjectSettings) -> ProjectSettings:
        result = ProjectSettings.from_dict(current.to_dict())
        result.language = self.language.currentText().strip()
        result.part_of_speech = self.part_of_speech.currentText().strip()
        result.system_prompt = self.prompt.toPlainText().strip()
        result.prompt_template = self._template_id
        result.sampling = self.get_sampling()
        result.validate()
        return result
