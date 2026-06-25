# SPDX-FileCopyrightText: Copyright (C) 2024-2025 沉默の金 <cmzj@cmzj.org>
# SPDX-License-Identifier: GPL-3.0-only
from dataclasses import dataclass
from typing import Optional, List

@dataclass
class MetadataResult:
    title: str
    artist: str
    album: str
    album_artist: Optional[str] = None
    date: Optional[str] = None
    genre: Optional[str] = None
    track_number: Optional[str] = None
    disc_number: Optional[str] = None
    composer: Optional[str] = None
    lyricist: Optional[str] = None
    cover_url: Optional[str] = None
    cover_data: Optional[bytes] = None
    comment: Optional[str] = None
    source: str = ""
    id: str = ""
