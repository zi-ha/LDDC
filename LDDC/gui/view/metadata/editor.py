# SPDX-FileCopyrightText: Copyright (C) 2024-2025 沉默の金 <cmzj@cmzj.org>
# SPDX-License-Identifier: GPL-3.0-only
import os
import re
import httpx
from difflib import SequenceMatcher
from PySide6.QtCore import Qt, Signal, Slot, QSize, QByteArray
from PySide6.QtGui import QAction, QIcon, QPixmap, QColor
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QScrollArea,
    QFrame,
    QGridLayout,
    QTextEdit,
)
from LDDC.core.api.metadata.handler import AudioMetadataHandler
from LDDC.core.api.metadata.models import MetadataResult
from LDDC.core.api.metadata.sources import KgMetadataSource, NeMetadataSource, QmMetadataSource
from LDDC.common.data.config import cfg
from LDDC.common.logger import logger

_FIELD_DEFS = [
    ("title", "标题"),
    ("artist", "艺术家"),
    ("album", "专辑"),
    ("album_artist", "专辑艺术家"),
    ("composer", "作曲者"),
    ("lyricist", "作词者"),
    ("date", "年份/日期"),
    ("genre", "流派"),
    ("track_number", "音轨号"),
    ("disc_number", "碟号"),
    ("comment", "备注"),
]

class FileListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            files = []
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if os.path.isfile(file_path):
                    if file_path.lower().endswith(('.mp3', '.flac', '.m4a', '.ogg', '.wav')):
                        files.append(file_path)
                elif os.path.isdir(file_path):
                     for root, dirs, filenames in os.walk(file_path):
                        for file in filenames:
                            if file.lower().endswith(('.mp3', '.flac', '.m4a', '.ogg', '.wav')):
                                files.append(os.path.join(root, file))
            
            # 调用父窗口的添加方法
            if self.parent():
                # QWidget -> QVBoxLayout -> QWidget -> QSplitter -> MusicMetadataEditorWidget
                # 这种查找方式不可靠，建议通过信号或直接传递回调
                # 这里简单处理，假设使用者会将 add_files_to_list 逻辑暴露或我们直接添加
                self.add_files_to_list(files)
            
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def add_files_to_list(self, files):
         for file_path in files:
            # 检查是否已存在
            items = self.findItems(os.path.basename(file_path), Qt.MatchFlag.MatchExactly)
            exists = False
            for item in items:
                if item.data(Qt.ItemDataRole.UserRole) == file_path:
                    exists = True
                    break
            
            if not exists:
                item = QListWidgetItem(os.path.basename(file_path))
                item.setData(Qt.ItemDataRole.UserRole, file_path)
                item.setToolTip(file_path)
                self.addItem(item)

class MusicMetadataEditorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_cover_data = None
        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.splitter)

        self.file_list_widget = QWidget()
        file_list_layout = QVBoxLayout(self.file_list_widget)
        file_list_layout.setContentsMargins(0, 0, 0, 0)

        file_list_label = QLabel("文件列表")
        file_list_layout.addWidget(file_list_label)

        self.file_list = FileListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.file_list.setDragDropMode(QListWidget.DragDropMode.DropOnly)
        self.file_list.setAcceptDrops(True)
        file_list_layout.addWidget(self.file_list)

        file_actions_layout = QHBoxLayout()
        self.add_files_btn = QPushButton("添加文件")
        self.add_folder_btn = QPushButton("添加文件夹")
        self.remove_file_btn = QPushButton("移除")

        self.add_files_btn.clicked.connect(self.add_files)
        self.add_folder_btn.clicked.connect(self.add_folder)
        self.remove_file_btn.clicked.connect(self.remove_selected_files)

        file_actions_layout.addWidget(self.add_files_btn)
        file_actions_layout.addWidget(self.add_folder_btn)
        file_actions_layout.addWidget(self.remove_file_btn)
        file_list_layout.addLayout(file_actions_layout)

        self.splitter.addWidget(self.file_list_widget)

        self.editor_widget = QWidget()
        editor_layout = QVBoxLayout(self.editor_widget)

        toolbar_layout = QHBoxLayout()
        self.save_btn = QPushButton("保存更改")
        self.match_net_btn = QPushButton("网络匹配")
        self.save_btn.clicked.connect(self.save_metadata)
        self.match_net_btn.clicked.connect(self.match_metadata_from_network)

        toolbar_layout.addWidget(self.save_btn)
        toolbar_layout.addWidget(self.match_net_btn)
        toolbar_layout.addStretch()
        editor_layout.addLayout(toolbar_layout)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self.scroll_content = QWidget()
        self.form_layout = QGridLayout(self.scroll_content)

        self.cover_label = QLabel("封面")
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setFixedSize(200, 200)
        self.cover_label.setStyleSheet("border: 1px solid gray; background-color: #f0f0f0;")
        self.cover_label.setAcceptDrops(True)
        self.cover_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.cover_label.customContextMenuRequested.connect(self._on_cover_context_menu)
        self.cover_label.installEventFilter(self)
        self.form_layout.addWidget(self.cover_label, 0, 0, 1, 2, Qt.AlignmentFlag.AlignCenter)

        self._editors = {}
        for i, (key, label) in enumerate(_FIELD_DEFS):
            lbl = QLabel(label)
            edit = QLineEdit()
            self.form_layout.addWidget(lbl, i + 1, 0)
            self.form_layout.addWidget(edit, i + 1, 1)
            self._editors[key] = edit

        self.form_layout.setColumnStretch(1, 1)

        self.file_list.currentItemChanged.connect(self.on_file_selected)

        scroll_area.setWidget(self.scroll_content)
        editor_layout.addWidget(scroll_area)

        self.splitter.addWidget(self.editor_widget)

        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 1)

    def save_metadata(self):
        current_item = self.file_list.currentItem()
        if not current_item:
            return

        file_path = current_item.data(Qt.ItemDataRole.UserRole)
        try:
            handler = AudioMetadataHandler(file_path)

            metadata = MetadataResult(
                title=self._editors["title"].text(),
                artist=self._editors["artist"].text(),
                album=self._editors["album"].text(),
                album_artist=self._editors["album_artist"].text(),
                composer=self._editors["composer"].text(),
                lyricist=self._editors["lyricist"].text(),
                date=self._editors["date"].text(),
                genre=self._editors["genre"].text(),
                track_number=self._editors["track_number"].text(),
                disc_number=self._editors["disc_number"].text(),
                comment=self._editors["comment"].text(),
                cover_data=self.current_cover_data,
            )

            handler.save(metadata)

        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存失败: {e}")

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择音乐文件",
            "",
            "Audio Files (*.mp3 *.flac *.m4a *.ogg *.wav);;All Files (*)"
        )
        if files:
            self.add_files_to_list(files)

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            # 简单递归遍历，实际应用可能需要更复杂的扫描逻辑
            import os
            music_files = []
            for root, dirs, files in os.walk(folder):
                for file in files:
                    if file.lower().endswith(('.mp3', '.flac', '.m4a', '.ogg', '.wav')):
                        music_files.append(os.path.join(root, file))
            self.add_files_to_list(music_files)

    def add_files_to_list(self, files):
        for file_path in files:
            # 检查是否已存在
            items = self.file_list.findItems(os.path.basename(file_path), Qt.MatchFlag.MatchExactly)
            exists = False
            for item in items:
                if item.data(Qt.ItemDataRole.UserRole) == file_path:
                    exists = True
                    break
            
            if not exists:
                item = QListWidgetItem(os.path.basename(file_path))
                item.setData(Qt.ItemDataRole.UserRole, file_path)
                item.setToolTip(file_path)
                self.file_list.addItem(item)

    def remove_selected_files(self):
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))

    def match_metadata_from_network(self):
        selected_items = self.file_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "提示", "请先在左侧选择要匹配的文件")
            return

        enabled_sources = cfg.get("metadata_search_sources", ["QM", "NE"])

        sources = []
        if "QM" in enabled_sources:
            sources.append(QmMetadataSource())
        if "NE" in enabled_sources:
            sources.append(NeMetadataSource())
        if "KG" in enabled_sources:
            sources.append(KgMetadataSource())

        if not sources:
            QMessageBox.warning(self, "警告", "未启用任何元数据搜索源，请在设置中配置")
            return

        success_count = 0
        failed_files = []
        current_item = self.file_list.currentItem()
        total = len(selected_items)

        progress = QProgressDialog("正在网络匹配...", "取消", 0, total, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        for i, item in enumerate(selected_items):
            if progress.wasCanceled():
                break

            progress.setValue(i)
            file_path = item.data(Qt.ItemDataRole.UserRole)
            progress.setLabelText(f"正在匹配: {os.path.basename(file_path)}")
            QApplication.processEvents()

            try:
                handler = AudioMetadataHandler(file_path)
                current_meta = handler.read()
                keyword = self.build_search_keyword(current_meta, file_path)
                best_match = self.find_best_match(keyword, sources)

                if not best_match:
                    failed_files.append(os.path.basename(file_path))
                    item.setBackground(QColor("#fff0f0"))
                    continue

                cover_data = self.download_cover_data(best_match.cover_url) if best_match.cover_url else None
                merged_metadata = self.merge_metadata(current_meta, best_match, cover_data)
                handler.save(merged_metadata)
                success_count += 1
                item.setBackground(QColor("#f0fff0"))

                if item == current_item:
                    self.apply_metadata_to_editor(merged_metadata)

            except Exception as e:
                logger.error(f"Error matching {file_path}: {e}")
                failed_files.append(os.path.basename(file_path))
                item.setBackground(QColor("#fff0f0"))

        progress.setValue(total)

        if success_count == 0:
            QMessageBox.warning(self, "完成", "网络匹配已完成，但没有可写入的匹配结果")
        elif failed_files:
            QMessageBox.information(self, "完成", f"网络匹配已完成，成功 {success_count} 个，失败 {len(failed_files)} 个")
        else:
            QMessageBox.information(self, "完成", f"网络匹配已完成，共成功 {success_count} 个")

    def build_search_keyword(self, current_meta: MetadataResult, file_path: str) -> str:
        keyword = f"{current_meta.artist or ''} {current_meta.title or ''}".strip()
        if keyword:
            return keyword
        return os.path.splitext(os.path.basename(file_path))[0]

    def find_best_match(self, keyword: str, sources: list) -> MetadataResult | None:
        candidates: list[tuple[float, MetadataResult]] = []
        for source in sources:
            results = source.search(keyword)
            if not results:
                continue
            for index, result in enumerate(results[:3]):
                score = self.calculate_match_score(keyword, result, index)
                candidates.append((score, result))
        if not candidates:
            return None
        best = max(candidates, key=lambda item: item[0])[1]
        return best

    def calculate_match_score(self, keyword: str, result: MetadataResult, index: int) -> float:
        searchable = f"{result.artist or ''} {result.title or ''}".strip().lower()
        similarity = SequenceMatcher(None, keyword.lower(), searchable).ratio()
        completeness = 0.0
        for value in (result.title, result.artist, result.album, result.date, result.track_number, result.genre):
            if value:
                completeness += 1.0
        if result.cover_url:
            completeness += 1.5
        return similarity * 10 + completeness - index * 0.5

    def merge_metadata(self, current_meta: MetadataResult, best_match: MetadataResult, cover_data: bytes | None) -> MetadataResult:
        artist = best_match.artist
        if isinstance(artist, list):
            artist = " / ".join(artist)
        match_year = self.extract_year(best_match.date)

        return MetadataResult(
            title=best_match.title or current_meta.title,
            artist=str(artist or current_meta.artist or ""),
            album=best_match.album or current_meta.album,
            album_artist=best_match.album_artist or current_meta.album_artist,
            composer=best_match.composer or current_meta.composer,
            lyricist=best_match.lyricist or current_meta.lyricist,
            date=match_year or current_meta.date,
            genre=best_match.genre or current_meta.genre,
            track_number=best_match.track_number or current_meta.track_number,
            disc_number=best_match.disc_number or current_meta.disc_number,
            comment=best_match.comment or current_meta.comment,
            cover_data=cover_data if cover_data is not None else current_meta.cover_data,
            source=best_match.source or current_meta.source,
            id=best_match.id or current_meta.id,
        )

    def extract_year(self, date_value: str | None) -> str | None:
        if not date_value:
            return None
        matched = re.search(r"(19|20)\d{2}", str(date_value))
        if matched:
            return matched.group(0)
        return None

    def apply_metadata_to_editor(self, metadata: MetadataResult):
        for key, _ in _FIELD_DEFS:
            value = getattr(metadata, key, "")
            self._editors[key].setText(value or "")
        self.current_cover_data = metadata.cover_data
        self._display_cover(metadata.cover_data)

    def download_cover_data(self, url: str) -> bytes | None:
        if not url:
            return None
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            response = httpx.get(url, headers=headers, timeout=10, follow_redirects=True)
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"Error loading cover from {url}: {e}")
            return None

    def _display_cover(self, cover_data: bytes | None):
        if cover_data:
            pixmap = QPixmap()
            pixmap.loadFromData(QByteArray(cover_data))
            if not pixmap.isNull():
                self.cover_label.setPixmap(
                    pixmap.scaled(
                        self.cover_label.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    ),
                )
                self.cover_label.setStyleSheet("")
                return
        self.cover_label.clear()
        self.cover_label.setText("无封面")
        self.cover_label.setStyleSheet("border: 1px solid gray; background-color: #f0f0f0;")

    def _on_cover_context_menu(self, pos):
        menu = QMenu(self)
        paste_action = menu.addAction("从剪贴板粘贴")
        save_action = menu.addAction("导出封面图片...")
        clear_action = menu.addAction("清除封面")

        action = menu.exec(self.cover_label.mapToGlobal(pos))
        if action == paste_action:
            self._paste_cover()
        elif action == save_action:
            self._export_cover()
        elif action == clear_action:
            self.current_cover_data = None
            self._display_cover(None)

    def _paste_cover(self):
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        if mime.hasImage():
            image = clipboard.image()
            if not image.isNull():
                ba = QByteArray()
                buf = image.save(ba, "JPG")
                if buf:
                    self.current_cover_data = ba.data()
                    self._display_cover(self.current_cover_data)
                    return
        if mime.hasUrls():
            for url in mime.urls():
                file_path = url.toLocalFile()
                if os.path.isfile(file_path):
                    try:
                        with open(file_path, "rb") as f:
                            self.current_cover_data = f.read()
                        self._display_cover(self.current_cover_data)
                        return
                    except Exception as e:
                        logger.error(f"Failed to load cover from clipboard file: {e}")
        QMessageBox.warning(self, "提示", "剪贴板中没有可用的图片")

    def _export_cover(self):
        if not self.current_cover_data:
            QMessageBox.warning(self, "提示", "没有封面数据可导出")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出封面", "cover.jpg", "JPEG (*.jpg);;PNG (*.png);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, "wb") as f:
                    f.write(self.current_cover_data)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出失败: {e}")

    def load_cover_from_url(self, url):
        cover_data = self.download_cover_data(url)
        if cover_data is None:
            return
        self.current_cover_data = cover_data
        self._display_cover(cover_data)

    def on_file_selected(self, current, previous):
        if not current:
            return

        file_path = current.data(Qt.ItemDataRole.UserRole)
        self.load_metadata(file_path)

    def load_metadata(self, file_path):
        try:
            handler = AudioMetadataHandler(file_path)
            metadata = handler.read()

            for key, _ in _FIELD_DEFS:
                value = getattr(metadata, key, "")
                if value is None:
                    value = ""
                self._editors[key].setText(str(value))

            self.current_cover_data = metadata.cover_data
            self._display_cover(metadata.cover_data)

        except Exception as e:
            QMessageBox.warning(self, "读取错误", f"无法读取文件元数据: {e}")

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if obj is self.cover_label:
            if event.type() == QEvent.Type.DragEnter:
                if event.mimeData().hasUrls() or event.mimeData().hasImage():
                    event.acceptProposedAction()
                    return True
            elif event.type() == QEvent.Type.Drop:
                mime = event.mimeData()
                if mime.hasUrls():
                    for url in mime.urls():
                        file_path = url.toLocalFile()
                        if os.path.isfile(file_path):
                            try:
                                with open(file_path, "rb") as f:
                                    self.current_cover_data = f.read()
                                self._display_cover(self.current_cover_data)
                                return True
                            except Exception as e:
                                logger.error(f"Failed to load dropped cover: {e}")
                elif mime.hasImage():
                    image = event.mimeData().imageData()
                    if image:
                        ba = QByteArray()
                        image.save(ba, "JPG")
                        self.current_cover_data = ba.data()
                        self._display_cover(self.current_cover_data)
                        return True
        return super().eventFilter(obj, event)

if __name__ == "__main__":
    app = QApplication([])
    window = MusicMetadataEditorWidget()
    window.resize(800, 600)
    window.show()
    app.exec()
