# SPDX-FileCopyrightText: Copyright (C) 2024-2025 沉默の金 <cmzj@cmzj.org>
# SPDX-License-Identifier: GPL-3.0-only
import mutagen
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TPE2, TCOM, TEXT, TDRC, TCON, TRCK, TPOS, COMM, USLT, APIC
from mutagen.mp4 import MP4, MP4Tags, MP4Cover
from mutagen.flac import FLAC, Picture
from mutagen.oggvorbis import OggVorbis
import os
import base64
from LDDC.common.logger import logger
from .models import MetadataResult

class AudioMetadataHandler:
    def __init__(self, file_path: str):
        self.file_path = file_path
        try:
            # mutagen.File 会自动根据文件头判断格式
            self.audio = mutagen.File(file_path)
            self.ext = os.path.splitext(file_path)[1].lower()
        except Exception as e:
            logger.error(f"Failed to load file {file_path}: {e}")
            self.audio = None
            self.ext = ""

    def read(self) -> MetadataResult:
        result = MetadataResult(title="", artist="", album="", source="Local")
        
        if not self.audio:
            return result

        try:
            if self.ext == '.mp3':
                # ID3 Tags
                if self.audio.tags:
                    tags = self.audio.tags
                    result.title = str(tags.get('TIT2', [''])[0])
                    result.artist = str(tags.get('TPE1', [''])[0])
                    result.album = str(tags.get('TALB', [''])[0])
                    result.album_artist = str(tags.get('TPE2', [''])[0])
                    result.composer = str(tags.get('TCOM', [''])[0])
                    result.lyricist = str(tags.get('TEXT', [''])[0])
                    
                    # 年份处理：TDRC (ID3v2.4) or TYER (ID3v2.3)
                    date = tags.get('TDRC')
                    if not date:
                        date = tags.get('TYER')
                    if date:
                        result.date = str(date[0])
                        
                    result.genre = str(tags.get('TCON', [''])[0])
                    result.track_number = str(tags.get('TRCK', [''])[0])
                    result.disc_number = str(tags.get('TPOS', [''])[0])
                    # 备注
                    comms = tags.getall('COMM')
                    if comms:
                        result.comment = str(comms[0])
                    
                    # 读取封面 (APIC)
                    for key in tags.keys():
                        if key.startswith('APIC:'):
                            apic = tags[key]
                            result.cover_data = apic.data
                            break
            
            elif self.ext in ('.flac', '.wav'):
                # FLAC / WAV (Vorbis Comments / RIFF INFO)
                result.title = self.audio.get('title', [''])[0]
                result.artist = self.audio.get('artist', [''])[0]
                result.album = self.audio.get('album', [''])[0]
                result.album_artist = self.audio.get('albumartist', [''])[0]
                result.composer = self.audio.get('composer', [''])[0]
                result.lyricist = self.audio.get('lyricist', [''])[0]
                result.date = self.audio.get('date', [''])[0]
                result.genre = self.audio.get('genre', [''])[0]
                result.track_number = self.audio.get('tracknumber', [''])[0]
                result.disc_number = self.audio.get('discnumber', [''])[0]
                result.comment = self.audio.get('comment', [''])[0]
                # 尝试其他常见字段名
                if not result.date: result.date = self.audio.get('year', [''])[0]
                if not result.comment: result.comment = self.audio.get('description', [''])[0]
                
                if self.audio.pictures:
                    result.cover_data = self.audio.pictures[0].data

            elif self.ext == '.ogg':
                result.title = self.audio.get('title', [''])[0]
                result.artist = self.audio.get('artist', [''])[0]
                result.album = self.audio.get('album', [''])[0]
                result.album_artist = self.audio.get('albumartist', [''])[0]
                result.composer = self.audio.get('composer', [''])[0]
                result.lyricist = self.audio.get('lyricist', [''])[0]
                result.date = self.audio.get('date', [''])[0]
                result.genre = self.audio.get('genre', [''])[0]
                result.track_number = self.audio.get('tracknumber', [''])[0]
                result.disc_number = self.audio.get('discnumber', [''])[0]
                result.comment = self.audio.get('comment', [''])[0]

                pic_b64 = self.audio.get('metadata_block_picture', [None])[0]
                if pic_b64:
                    try:
                        pic_data = base64.b64decode(pic_b64)
                        picture = Picture(pic_data)
                        result.cover_data = picture.data
                    except Exception:
                        pass

            elif self.ext == '.m4a':
                # MP4 Tags
                tags = self.audio.tags
                if tags:
                    result.title = tags.get('\xa9nam', [''])[0]
                    result.artist = tags.get('\xa9ART', [''])[0]
                    result.album = tags.get('\xa9alb', [''])[0]
                    result.album_artist = tags.get('aART', [''])[0]
                    result.composer = tags.get('\xa9wrt', [''])[0]
                    lyricist_raw = tags.get('----:com.apple.iTunes:LYRICIST', [b''])[0]
                    result.lyricist = lyricist_raw.decode('utf-8', errors='replace') if isinstance(lyricist_raw, bytes) else str(lyricist_raw)
                    result.date = tags.get('\xa9day', [''])[0]
                    result.genre = tags.get('\xa9gen', [''])[0]
                    # trkn and disk are tuples
                    trkn = tags.get('trkn', [(0, 0)])[0]
                    if trkn[0] > 0:
                        result.track_number = f"{trkn[0]}/{trkn[1]}" if trkn[1] > 0 else str(trkn[0])
                    disk = tags.get('disk', [(0, 0)])[0]
                    if disk[0] > 0:
                        result.disc_number = f"{disk[0]}/{disk[1]}" if disk[1] > 0 else str(disk[0])
                    result.comment = tags.get('\xa9cmt', [''])[0]
                    
                    # 封面
                    covers = tags.get('covr')
                    if covers:
                        result.cover_data = covers[0]
        
        except Exception as e:
            logger.error(f"Error reading metadata for {self.file_path}: {e}")

        # 如果标题为空，尝试使用文件名
        if not result.title:
            result.title = os.path.splitext(os.path.basename(self.file_path))[0]

        return result

    def save(self, metadata: MetadataResult):
        if not self.audio:
            return

        try:
            if self.ext == '.mp3':
                if self.audio.tags is None:
                    self.audio.add_tags()
                tags = self.audio.tags
                tags["TIT2"] = TIT2(encoding=3, text=metadata.title or "")
                tags["TPE1"] = TPE1(encoding=3, text=metadata.artist or "")
                tags["TALB"] = TALB(encoding=3, text=metadata.album or "")
                if metadata.album_artist:
                    tags["TPE2"] = TPE2(encoding=3, text=metadata.album_artist)
                if metadata.date:
                    tags["TDRC"] = TDRC(encoding=3, text=metadata.date)
                if metadata.genre:
                    tags["TCON"] = TCON(encoding=3, text=metadata.genre)
                if metadata.track_number:
                    tags["TRCK"] = TRCK(encoding=3, text=metadata.track_number)
                if metadata.disc_number:
                    tags["TPOS"] = TPOS(encoding=3, text=metadata.disc_number)
                tags.delall("COMM")
                if metadata.comment:
                    tags.add(COMM(encoding=3, lang="eng", desc="", text=metadata.comment))
                if metadata.composer:
                    tags["TCOM"] = TCOM(encoding=3, text=metadata.composer)
                if metadata.lyricist:
                    tags["TEXT"] = TEXT(encoding=3, text=metadata.lyricist)
                tags.delall("APIC")
                if metadata.cover_data:
                    tags.add(APIC(encoding=3, mime=self._guess_mime_type(metadata.cover_data), type=3, desc="Cover", data=metadata.cover_data))

            elif self.ext in ('.flac', '.wav'):
                self.audio['title'] = metadata.title
                self.audio['artist'] = metadata.artist
                self.audio['album'] = metadata.album
                if metadata.album_artist: self.audio['albumartist'] = metadata.album_artist
                if metadata.composer: self.audio['composer'] = metadata.composer
                if metadata.lyricist: self.audio['lyricist'] = metadata.lyricist
                if metadata.date: self.audio['date'] = metadata.date
                if metadata.genre: self.audio['genre'] = metadata.genre
                if metadata.track_number: self.audio['tracknumber'] = metadata.track_number
                if metadata.disc_number: self.audio['discnumber'] = metadata.disc_number
                if metadata.comment: self.audio['comment'] = metadata.comment
                if metadata.cover_data:
                    picture = Picture()
                    picture.type = 3
                    picture.mime = self._guess_mime_type(metadata.cover_data)
                    picture.data = metadata.cover_data
                    self.audio.clear_pictures()
                    self.audio.add_picture(picture)

            elif self.ext == '.ogg':
                self.audio['title'] = metadata.title
                self.audio['artist'] = metadata.artist
                self.audio['album'] = metadata.album
                if metadata.album_artist: self.audio['albumartist'] = metadata.album_artist
                if metadata.composer: self.audio['composer'] = metadata.composer
                if metadata.lyricist: self.audio['lyricist'] = metadata.lyricist
                if metadata.date: self.audio['date'] = metadata.date
                if metadata.genre: self.audio['genre'] = metadata.genre
                if metadata.track_number: self.audio['tracknumber'] = metadata.track_number
                if metadata.disc_number: self.audio['discnumber'] = metadata.disc_number
                if metadata.comment: self.audio['comment'] = metadata.comment
                if metadata.cover_data:
                    picture = Picture()
                    picture.type = 3
                    picture.mime = self._guess_mime_type(metadata.cover_data)
                    picture.data = metadata.cover_data
                    self.audio['metadata_block_picture'] = [base64.b64encode(picture.write()).decode("ascii")]

            elif self.ext == '.m4a':
                tags = self.audio.tags
                if tags is None:
                    self.audio.add_tags()
                    tags = self.audio.tags
                tags['\xa9nam'] = metadata.title
                tags['\xa9ART'] = metadata.artist
                tags['\xa9alb'] = metadata.album
                if metadata.album_artist: tags['aART'] = metadata.album_artist
                if metadata.composer: tags['\xa9wrt'] = metadata.composer
                if metadata.lyricist: tags['----:com.apple.iTunes:LYRICIST'] = [metadata.lyricist.encode('utf-8')]
                if metadata.date: tags['\xa9day'] = metadata.date
                if metadata.genre: tags['\xa9gen'] = metadata.genre
                if metadata.track_number:
                    trkn_parts = metadata.track_number.split('/')
                    tags['trkn'] = [(int(trkn_parts[0]), int(trkn_parts[1]) if len(trkn_parts) > 1 else 0)]
                if metadata.disc_number:
                    disk_parts = metadata.disc_number.split('/')
                    tags['disk'] = [(int(disk_parts[0]), int(disk_parts[1]) if len(disk_parts) > 1 else 0)]
                if metadata.comment: tags['\xa9cmt'] = metadata.comment
                if metadata.cover_data:
                    cover_format = MP4Cover.FORMAT_JPEG if self._guess_mime_type(metadata.cover_data) == "image/jpeg" else MP4Cover.FORMAT_PNG
                    tags['covr'] = [MP4Cover(metadata.cover_data, imageformat=cover_format)]

            self.audio.save()

        except Exception as e:
            logger.error(f"Error saving metadata for {self.file_path}: {e}")

    def _guess_mime_type(self, data: bytes) -> str:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        return "image/jpeg"
