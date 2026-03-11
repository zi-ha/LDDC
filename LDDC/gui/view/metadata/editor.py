# SPDX-FileCopyrightText: Copyright (C) 2024-2025 沉默の金 <cmzj@cmzj.org>
# SPDX-License-Identifier: GPL-3.0-only
import os
import re
import httpx
from difflib import SequenceMatcher
from PySide6.QtCore import Qt, Signal, Slot, QSize, QByteArray
from PySide6.QtGui import QAction, QIcon, QPixmap
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
        # 主布局使用水平分割器，左侧为文件列表，右侧为编辑区域
        main_layout = QHBoxLayout(self)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.splitter)

        # 左侧文件列表区域
        self.file_list_widget = QWidget()
        file_list_layout = QVBoxLayout(self.file_list_widget)
        file_list_layout.setContentsMargins(0, 0, 0, 0)
        
        # 文件列表标题
        file_list_label = QLabel("文件列表")
        file_list_layout.addWidget(file_list_label)

        # 文件列表控件
        self.file_list = FileListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.file_list.setDragDropMode(QListWidget.DragDropMode.DropOnly)
        self.file_list.setAcceptDrops(True)
        file_list_layout.addWidget(self.file_list)

        # 底部操作按钮（如添加文件、删除文件）
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

        # 右侧元数据编辑区域
        self.editor_widget = QWidget()
        editor_layout = QVBoxLayout(self.editor_widget)
        
        # 顶部工具栏区域（保存、网络匹配等）
        toolbar_layout = QHBoxLayout()
        self.save_btn = QPushButton("保存更改")
        self.match_net_btn = QPushButton("网络匹配")
        self.save_btn.clicked.connect(self.save_metadata)
        self.match_net_btn.clicked.connect(self.match_metadata_from_network)

        toolbar_layout.addWidget(self.save_btn)
        toolbar_layout.addWidget(self.match_net_btn)
        toolbar_layout.addStretch()
        editor_layout.addLayout(toolbar_layout)

        # 滚动区域，防止内容过多显示不下
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
        self.scroll_content = QWidget()
        self.form_layout = QGridLayout(self.scroll_content)
        
        # 封面显示与编辑
        self.cover_label = QLabel("封面")
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setFixedSize(200, 200)
        self.cover_label.setStyleSheet("border: 1px solid gray; background-color: #f0f0f0;")
        self.form_layout.addWidget(self.cover_label, 0, 0, 1, 2, Qt.AlignmentFlag.AlignCenter)

        # 元数据字段
        self.title_edit = self.create_field("标题", 1)
        self.artist_edit = self.create_field("艺术家", 2)
        self.album_edit = self.create_field("专辑", 3)
        self.album_artist_edit = self.create_field("专辑艺术家", 4)
        
        self.date_edit = self.create_field("年份/日期", 5)
        self.genre_edit = self.create_field("流派", 6)
        self.track_number_edit = self.create_field("音轨号", 7)
        self.disc_number_edit = self.create_field("碟号", 8)
        
        self.comment_edit = self.create_field("备注", 9)
        
        self.form_layout.setColumnStretch(1, 1)

        # 信号连接
        self.file_list.currentItemChanged.connect(self.on_file_selected)
        
        scroll_area.setWidget(self.scroll_content)
        editor_layout.addWidget(scroll_area)

        self.splitter.addWidget(self.editor_widget)
        
        # 设置初始分割比例：右侧编辑区域设置为整体的 1/3
        # 左侧:右侧 = 2:1
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 1)

    def save_metadata(self):
        current_item = self.file_list.currentItem()
        if not current_item:
            return

        file_path = current_item.data(Qt.ItemDataRole.UserRole)
        try:
            handler = AudioMetadataHandler(file_path)
            
            # 从界面获取最新数据
            metadata = MetadataResult(
                title=self.title_edit.text(),
                artist=self.artist_edit.text(),
                album=self.album_edit.text(),
                album_artist=self.album_artist_edit.text(),
                date=self.date_edit.text(),
                genre=self.genre_edit.text(),
                track_number=self.track_number_edit.text(),
                disc_number=self.disc_number_edit.text(),
                comment=self.comment_edit.text(),
                cover_data=self.current_cover_data # 传递暂存的封面数据
            )
            
            # 保存元数据
            handler.save(metadata)
            # QMessageBox.information(self, "成功", "元数据保存成功！") # 自动化流程中可移除弹窗
            
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

        # 从配置中读取启用的源
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

        for item in selected_items:
            file_path = item.data(Qt.ItemDataRole.UserRole)
            try:
                handler = AudioMetadataHandler(file_path)
                current_meta = handler.read()
                keyword = self.build_search_keyword(current_meta, file_path)
                best_match = self.find_best_match(keyword, sources)

                if not best_match:
                    print(f"No match found for {keyword}")
                    failed_files.append(os.path.basename(file_path))
                    continue

                cover_data = self.download_cover_data(best_match.cover_url) if best_match.cover_url else None
                merged_metadata = self.merge_metadata(current_meta, best_match, cover_data)
                handler.save(merged_metadata)
                success_count += 1

                if item == current_item:
                    self.apply_metadata_to_editor(merged_metadata)

            except Exception as e:
                print(f"Error matching {file_path}: {e}")
                failed_files.append(os.path.basename(file_path))

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
            print(f"Trying source: {type(source).__name__}")
            results = source.search(keyword)
            if not results:
                continue
            for index, result in enumerate(results[:3]):
                score = self.calculate_match_score(keyword, result, index)
                candidates.append((score, result))
        if not candidates:
            return None
        best = max(candidates, key=lambda item: item[0])[1]
        print(f"Match found: {best.title} - {best.artist}")
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
        self.title_edit.setText(metadata.title or "")
        self.artist_edit.setText(metadata.artist or "")
        self.album_edit.setText(metadata.album or "")
        self.album_artist_edit.setText(metadata.album_artist or "")
        self.date_edit.setText(metadata.date or "")
        self.genre_edit.setText(metadata.genre or "")
        self.track_number_edit.setText(metadata.track_number or "")
        self.disc_number_edit.setText(metadata.disc_number or "")
        self.comment_edit.setText(metadata.comment or "")
        self.current_cover_data = metadata.cover_data

        if metadata.cover_data:
            pixmap = QPixmap()
            pixmap.loadFromData(QByteArray(metadata.cover_data))
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

    def download_cover_data(self, url: str) -> bytes | None:
        if not url:
            return None
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            response = httpx.get(url, headers=headers, timeout=10, follow_redirects=True)
            response.raise_for_status()
            return response.content
        except Exception as e:
            print(f"Error loading cover from {url}: {e}")
            return None

    def load_cover_from_url(self, url):
        cover_data = self.download_cover_data(url)
        if cover_data is None:
            return
        self.current_cover_data = cover_data
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
        else:
            print(f"Failed to load image data from {url}")

    def on_file_selected(self, current, previous):
        if not current:
            return
            
        file_path = current.data(Qt.ItemDataRole.UserRole)
        self.load_metadata(file_path)

    def load_metadata(self, file_path):
        try:
            handler = AudioMetadataHandler(file_path)
            metadata = handler.read()
            
            self.title_edit.setText(metadata.title or "")
            self.artist_edit.setText(metadata.artist or "")
            self.album_edit.setText(metadata.album or "")
            self.album_artist_edit.setText(metadata.album_artist or "")
            self.date_edit.setText(metadata.date or "")
            self.genre_edit.setText(metadata.genre or "")
            self.track_number_edit.setText(metadata.track_number or "")
            self.disc_number_edit.setText(metadata.disc_number or "")
            self.comment_edit.setText(metadata.comment or "") if hasattr(metadata, 'comment') else self.comment_edit.clear()
            
            # 封面处理
            self.current_cover_data = None # 重置暂存的封面数据
            if hasattr(metadata, 'cover_data') and metadata.cover_data:
                self.current_cover_data = metadata.cover_data # 暂存本地读取的封面
                pixmap = QPixmap()
                pixmap.loadFromData(QByteArray(metadata.cover_data))
                if not pixmap.isNull():
                    self.cover_label.setPixmap(pixmap.scaled(
                        self.cover_label.size(), 
                        Qt.AspectRatioMode.KeepAspectRatio, 
                        Qt.TransformationMode.SmoothTransformation
                    ))
                    self.cover_label.setStyleSheet("") # 清除边框背景
                else:
                    self.cover_label.setText("无效封面")
                    self.cover_label.setStyleSheet("border: 1px solid gray; background-color: #f0f0f0;")
            else:
                self.cover_label.setText("无封面")
                self.cover_label.setStyleSheet("border: 1px solid gray; background-color: #f0f0f0;")
            
        except Exception as e:
            QMessageBox.warning(self, "读取错误", f"无法读取文件元数据: {e}")

    def create_field(self, label_text, row):
        label = QLabel(label_text)
        edit = QLineEdit()
        self.form_layout.addWidget(label, row, 0)
        self.form_layout.addWidget(edit, row, 1)
        return edit

if __name__ == "__main__":
    app = QApplication([])
    window = MusicMetadataEditorWidget()
    window.resize(800, 600)
    window.show()
    app.exec()
