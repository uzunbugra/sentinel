# =============================================================================
# SentinelFlow - SAML-D display identities (ML-02)
# =============================================================================
"""
Display-only IBAN and name per SAML-D account, derived deterministically from the
account id (no RNG). They are never model input. Split out of ``samld_dataset``.
"""

from __future__ import annotations

import hashlib

import pandas as pd

# --- Display identities --------------------------------------------------------
# Fictional 5-digit bank codes (not assigned to real Turkish banks). Name lists are
# common Turkish names; FIRST_NAMES is 40 male then 40 female names.
DISPLAY_BANK_CODES: tuple[str, ...] = tuple(f"9{n:04d}" for n in range(1, 12))
# fmt: off
FIRST_NAMES: tuple[str, ...] = (
    "Ahmet", "Mehmet", "Mustafa", "Ali", "Hüseyin", "Hasan", "İbrahim", "Murat", "Ömer",
    "Yusuf", "Emre", "Burak", "Can", "Cem", "Deniz", "Eren", "Fatih", "Gökhan", "Halil",
    "Kemal", "Kerem", "Levent", "Onur", "Orhan", "Serkan", "Sinan", "Tolga", "Uğur", "Volkan",
    "Yasin", "Bora", "Tuncay", "Barış", "Enes", "Furkan", "Hakan", "Selim", "Tarık", "Umut",
    "Berk", "Ayşe", "Fatma", "Emine", "Hatice", "Zeynep", "Elif", "Meryem", "Şerife", "Zehra",
    "Sultan", "Hanife", "Merve", "Büşra", "Esra", "Gizem", "Selin", "Ece", "Derya", "Ebru",
    "Özlem", "Pınar", "Seda", "Tuğba", "Yasemin", "Nur", "Aslı", "Burcu", "Cansu", "Dilek",
    "Gamze", "İrem", "Kübra", "Melike", "Neslihan", "Sevgi", "Sibel", "Şule", "Tuba", "Yağmur",
    "Zerrin",
)
LAST_NAMES: tuple[str, ...] = (
    "Yılmaz", "Kaya", "Demir", "Şahin", "Çelik", "Yıldız", "Yıldırım", "Öztürk", "Aydın",
    "Özdemir", "Arslan", "Doğan", "Kılıç", "Aslan", "Çetin", "Kara", "Koç", "Kurt", "Özkan",
    "Şimşek", "Polat", "Özcan", "Korkmaz", "Çakır", "Erdoğan", "Yavuz", "Can", "Acar", "Şen",
    "Aktaş", "Güler", "Yalçın", "Güneş", "Kartal", "Bulut", "Keskin", "Ünal", "Turan", "Gül",
    "Özer", "Işık", "Kaplan", "Avcı", "Sarı", "Aydemir", "Taş", "Köse", "Yüksel", "Ateş",
    "Aksoy", "Sezer", "Karataş", "Erdem", "Tunç", "Altın", "Toprak", "Karaca", "Özgür", "Duman",
    "Akın",
)
# fmt: on
DOUBLE_FIRST_NAME_PERCENT = 45


def _iban(account: str, bank_code: str) -> str:
    """TR IBAN: TR + mod-97 check digits + bank code + reserve 0 + 16-digit account."""
    bban = f"{bank_code}0{int(account):016d}"
    # Move "TR00" to the end and replace letters (T=29, R=27) before mod 97.
    check = 98 - int(f"{bban}292700") % 97
    return f"TR{check:02d}{bban}"


def _display_identity(account: str, version: str) -> tuple[str, str]:
    digest = hashlib.sha256(f"{version}:{account}".encode()).digest()
    pick = int.from_bytes(digest[:8], "big")
    bank = DISPLAY_BANK_CODES[pick % len(DISPLAY_BANK_CODES)]
    first = FIRST_NAMES[(pick >> 8) % len(FIRST_NAMES)]
    last = LAST_NAMES[(pick >> 16) % len(LAST_NAMES)]
    name = f"{first} {last}"
    if (pick >> 24) % 100 < DOUBLE_FIRST_NAME_PERCENT:
        # Second first name of the same gender half as the first one.
        half = len(FIRST_NAMES) // 2
        offset = 0 if FIRST_NAMES.index(first) < half else half
        second = FIRST_NAMES[offset + (pick >> 32) % half]
        if second != first:
            name = f"{first} {second} {last}"
    return _iban(account, bank), name


def display_identities(accounts: pd.Series, version: str) -> pd.DataFrame:
    """IBAN and name per unique account, deterministic in ``version`` and the account id."""
    unique = pd.unique(accounts.astype(str))
    pairs = [_display_identity(account, version) for account in unique]
    return pd.DataFrame(pairs, index=pd.Index(unique, name="account"), columns=["iban", "name"])
