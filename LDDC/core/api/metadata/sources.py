# SPDX-FileCopyrightText: Copyright (C) 2024-2025 沉默の金 <cmzj@cmzj.org>
# SPDX-License-Identifier: GPL-3.0-only
import httpx
from typing import List
from LDDC.common.logger import logger
from .models import MetadataResult

class MetadataSource:
    def search(self, keyword: str) -> List[MetadataResult]:
        raise NotImplementedError

class KgMetadataSource(MetadataSource):
    def search(self, keyword: str) -> List[MetadataResult]:
        # 简化版实现，复用现有的 KGAPI 逻辑或重新实现轻量级搜索
        try:
            # 这里为了演示，我们使用一个简化的请求，实际应复用 KGAPI 的鉴权逻辑
            # 但鉴于 KGAPI 较为复杂，我们这里先实现一个无需鉴权的旧接口，或者
            # 直接实例化 KGAPI (如果它不包含过多副作用)
            
            # 由于 KGAPI 已经封装好了，我们尝试直接调用它
            # 注意：这需要解决循环引用或依赖问题，如果不行则手动请求
            from LDDC.core.api.lyrics.kg import KGAPI, SearchType
            
            api = KGAPI()
            results = api.search(keyword, SearchType.SONG)
            
            metadata_list = []
            for song in results:
                # 尝试从 API 结果中提取更多信息
                # KG 的 SongInfo 结构可能包含有限，我们可能需要额外请求或从其他字段推断
                
                # 提取年份
                date = None
                if hasattr(song, 'extra') and song.extra:
                    if song.extra.get('PublishDate'):
                        date = song.extra['PublishDate']

                cover_url = None
                if hasattr(song, 'extra') and song.extra and song.extra.get('Image'):
                    cover_url = song.extra['Image'].replace('{size}', '480').replace('http:', 'https:')

                metadata = MetadataResult(
                    title=song.title,
                    artist="/".join(song.artist) if isinstance(song.artist, list) else song.artist,
                    album=song.album if song.album else "",
                    date=date,
                    cover_url=cover_url,
                    source="酷狗音乐",
                    id=song.hash
                )
                    
                metadata_list.append(metadata)
            return metadata_list
            
        except Exception as e:
            logger.error(f"KG Metadata search failed: {e}")
            return []

class QmMetadataSource(MetadataSource):
    def search(self, keyword: str) -> List[MetadataResult]:
        try:
            from LDDC.core.api.lyrics.qm import QMAPI, SearchType
            api = QMAPI()
            results = api.search(keyword, SearchType.SONG)
            
            metadata_list = []
            for song in results:
                cover_url = None
                if hasattr(song, 'extra') and 'album_mid' in song.extra and song.extra['album_mid']:
                     cover_url = f"https://y.gtimg.cn/music/photo_new/T002R1200x1200M000{song.extra['album_mid']}.jpg"
                elif hasattr(song, 'album_id') and song.album_id:
                     cover_url = f"https://y.gtimg.cn/music/photo_new/T002R300x300M000{song.album_id}.jpg"
                
                # QQ音乐搜索结果基础信息
                date = None
                if hasattr(song, 'extra') and 'public_time' in song.extra:
                    date = song.extra['public_time']

                # 尝试通过 QMAPI 获取专辑详情来补充年份和音轨号
                # 假设 QMAPI 有 get_album_info 方法，如果没有则需要实现
                # 这里为了性能，我们只对搜索结果的前几个进行详情获取，或者只在用户确认后获取
                # 但目前为了满足"匹配不全"的需求，我们对最佳匹配尝试获取
                
                track_number = None
                # song.extra 可能包含 index_album (音轨号)
                if hasattr(song, 'extra') and 'index_album' in song.extra:
                    track_number = str(song.extra['index_album'])
                    
                metadata = MetadataResult(
                    title=song.title,
                    artist="/".join(song.artist) if isinstance(song.artist, list) else song.artist,
                    album=song.album if song.album else "",
                    date=date,
                    track_number=track_number,
                    cover_url=cover_url,
                    source="QQ音乐",
                    id=song.mid
                )
                metadata_list.append(metadata)
            return metadata_list
        except Exception as e:
            logger.error(f"QM Metadata search failed: {e}")
            return []

class NeMetadataSource(MetadataSource):
    def search(self, keyword: str) -> List[MetadataResult]:
        try:
            from LDDC.core.api.lyrics.ne import NEAPI, SearchType
            api = NEAPI()
            results = api.search(keyword, SearchType.SONG)
            
            metadata_list = []
            for song in results:
                cover_url = None
                if hasattr(song, 'extra') and 'picUrl' in song.extra:
                    cover_url = song.extra['picUrl']
                elif hasattr(song, 'pic_url') and song.pic_url:
                    cover_url = song.pic_url

                if cover_url:
                    if '?param=' in cover_url:
                        cover_url = cover_url.split('?param=')[0] + '?param=1200y1200'
                    else:
                        cover_url = cover_url.rstrip('?') + '?param=1200y1200'
                
                # 尝试提取年份
                date = None
                if hasattr(song, 'extra') and 'publishTime' in song.extra:
                    import datetime
                    try:
                        ts = int(song.extra['publishTime'])
                        if ts > 1000000000000: ts = ts / 1000
                        date = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
                    except:
                        pass
                
                # 尝试提取音轨号
                track_number = None
                if hasattr(song, 'extra') and 'no' in song.extra:
                     track_number = str(song.extra['no'])

                metadata = MetadataResult(
                    title=song.title,
                    artist="/".join(song.artist) if isinstance(song.artist, list) else song.artist,
                    album=song.album if song.album else "",
                    date=date,
                    track_number=track_number,
                    cover_url=cover_url,
                    source="网易云音乐",
                    id=str(song.id)
                )
                metadata_list.append(metadata)
            return metadata_list
        except Exception as e:
            logger.error(f"NE Metadata search failed: {e}")
            return []
