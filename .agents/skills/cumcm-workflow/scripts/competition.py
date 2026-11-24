"""Competition identity shared by paper templates and submission checks."""
import re
import unicodedata


def is_huawei_competition(competition: str) -> bool:
    name = unicodedata.normalize("NFKC", competition).casefold()
    compact = re.sub(r"\s+", "", name)
    return (
        "华为杯" in compact
        or "研究生数学建模竞赛" in compact
        or bool(re.search(r"(?<![a-z0-9])(?:huawei[\s-]+cup|gmcm|cpgmcm|cpmcm)(?![a-z0-9])", name))
        or "china postgraduate mathematical contest in modeling" in " ".join(name.split())
    )
