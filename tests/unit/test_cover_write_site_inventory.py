"""封面／衍生圖「寫入點」清單的機械對帳（AST，Codex PR#125 round-2 P1 的防再犯閘）。

## 為什麼是這一支測試存在的理由

同一個根因在 feature/112b 出現了**三次**：

1. `2338c62d`（pre-merge red-team）：`_write_cover_copy` 是第 8 個同檔碰撞點，
   CD-112-8 的交棒稽核沒抓到。
2. `a552f674`（Codex PR#125 round-1 P2）：同一個點的 `src == dst` 捷徑會把
   「檔案已不在」報成成功。
3. Codex PR#125 round-2 P1：curator sidecar 的兩處 `copy2(sidecar, dst)`
   ——把使用者親手挑的 `-poster` 用機器裁的封面就地覆蓋。

三次的共同成因**不是**寫碼的人不小心，是**稽核方法**：T3 §H-5 的做法是
`grep "same_target_verdict("`，那只找得到**已經有保護的點**，永遠找不到
「該有卻沒有的點」；`core/cover_layout.py` 交棒清單的判準又寫成
「`copy2(cover, *)` / `crop_to_poster(cover, *)`」——來源不是 cover 的寫入點
（curator sidecar → 同樣那兩個目的檔）結構上對它隱形。

所以這一支把清單**反過來寫**：列舉三個封面模組裡**每一個** `copy2` /
`copyfile` / `crop_to_poster` 呼叫點，與一份**硬編碼**的預期清單逐格對帳。
新增任何寫入點（不論來源是誰）都會轉紅，逼人回到
`core/cover_layout.py` 的交棒清單那一段，決定它該不該有 preflight。

## 為什麼是 pytest 而不是 lint

CLAUDE.md「Lint 守衛規則」的分流表：「某個 Python 函式的行為 / 源碼語意（AST）」
→ pytest。本檔斷言的是 Python AST（呼叫點歸屬），不是 HTML/JS/CSS 字面字串，
不落在 lint 那一側，也不觸發 SA-pre-6 的 content-based 偵測。

## 這支測試**不**宣稱什麼（誠實邊界）

它只保證「清單沒有被無聲地擴充」，**不**保證每個呼叫點的參數配對正確
（那要資料流分析，脆弱且會製造假綠）。實際的同檔語意由
`test_readonly_producer.py::TestCollocatedCuratorSidecarPassthrough`、
`TestWriteMediaImagesFanartPreflightSamefileGuard`、`test_enricher.py`／
`test_organizer.py` 的對應守衛用真檔案驗。已知缺口（與
`scripts/py_function_size_lint.py` 的 EXEMPTIONS 同性質）：新寫入點可以直接
被加進下面的預期清單而繞過——擋不掉的是判斷力，擋得掉的是**無聲**新增。
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# 掃描範圍＝會寫 stem 級衍生圖（正典封面 / -poster / -fanart）的三個模組。
_MODULES = (
    'core/enricher.py',
    'core/organizer.py',
    'core/readonly_producer.py',
)

_WRITE_CALLS = ('copy2', 'copyfile', 'crop_to_poster', 'atomic_move')
# `atomic_move`（144-T0 新增，`core/atomic_write.py`）為什麼也要進這張清單：
# 它內部的 `shutil.copy2`（EXDEV fallback）住在**本守衛掃不到的檔案**裡，所以
# 若不在這裡收，任何人只要在這三支模組寫 `atomic_move(cover, poster_dest)`，
# 就能新增一個對本守衛**完全隱形**的衍生圖寫入點——比直接寫 `copy2` 更隱蔽
# （連呼叫名稱都不在關鍵字裡），而且後果更不可逆：`atomic_move` 成功後會
# `unlink(src)`，`copy2` 至少還留著來源。
# ⚠️ 這條的判準與其他三個一樣是**呼叫名稱**，不是「它實際寫到哪」——
# 收在這裡的用意是「新增就轉紅、逼人回來想一次」，不是證明它一定有害。
_PREFLIGHT = 'same_target_verdict'

# 硬編碼的預期清單（BE-TEST-09：**不得**由掃描結果反推，否則 missing 恆為空
# 集合、結構上不可能轉紅）。key = (檔案, 所屬函式, 被呼叫名稱)，value = 次數。
# 每一格的理由見 core/cover_layout.py 的「交棒清單」表。
_EXPECTED_WRITE_SITES = {
    ('core/enricher.py', '_write_external_images', 'copy2'): 1,              # ③ cover → fanart
    ('core/enricher.py', '_write_external_images', 'crop_to_poster'): 1,     # ④ cover → poster
    ('core/organizer.py', 'crop_to_poster', 'copy2'): 1,                     # 葉節點：已是直向、直接複製
    ('core/organizer.py', 'organize_file', 'atomic_move'): 1,               # 144-T0：影片本體搬進片庫，非衍生圖
    ('core/organizer.py', 'generate_jellyfin_images', 'copy2'): 1,           # ① cover → fanart
    ('core/organizer.py', 'generate_jellyfin_images', 'crop_to_poster'): 1,  # ② cover → poster
    ('core/readonly_producer.py', '_copy_curator_sidecar', 'copy2'): 1,      # ⑨⑩ curator sidecar → slot
    ('core/readonly_producer.py', '_write_cover_copy', 'copyfile'): 1,       # ⑧ 來源封面 → 正典位置
    ('core/readonly_producer.py', '_write_media_images', 'copy2'): 1,        # ⑤ cover → fanart
    ('core/readonly_producer.py', '_write_media_images', 'crop_to_poster'): 1,  # ⑥ cover → poster
}

# 每個 owner **預期的 preflight 次數**（Codex PR#125 round-3 P2）。
#
# 為什麼要數量、不能只用集合做存在性比對：`_write_media_images` 一個函式裡有
# 兩個寫入點（fanart 的 copy2、poster 的 crop_to_poster），各自需要**自己那一次**
# preflight。集合式的「這個函式有沒有呼叫過 same_target_verdict」只要留一個就
# 恆真——拿掉 poster 那道保護、留著 fanart 的，守衛依然全綠，**結構上不可能
# 轉紅**。那正是本 branch 已經踩過兩次的假綠家族（0.13.3 的「白名單反推自動
# 吸收缺口」、pre-merge Stage 2 P1 的「假前提關掉反向鎖」）。`_write_external_images`
# 與 `generate_jellyfin_images` 是同一個形狀。
#
# 這裡刻意鎖「每個 owner 的 preflight 次數 == 寫入點次數」而不是做資料流分析
# 去證明「第 N 個寫入點配到第 N 個 preflight」：後者需要跨分支的別名追蹤，脆弱
# 且本身就會製造假綠。次數對帳擋得住「無聲少一道」，配對正確性由
# `test_readonly_producer.py` / `test_enricher.py` / `test_organizer.py` 的真檔案
# 行為守衛負責——兩層各司其職，這是本檔「誠實邊界」那段的延伸。
_EXPECTED_PREFLIGHTS = {
    ('core/enricher.py', '_write_external_images'): 2,          # ③④ 各一
    ('core/organizer.py', 'generate_jellyfin_images'): 2,       # ①② 各一
    ('core/readonly_producer.py', '_copy_curator_sidecar'): 1,  # ⑨⑩ 共用同一個 choke point
    ('core/readonly_producer.py', '_write_cover_copy'): 1,      # ⑧
    ('core/readonly_producer.py', '_write_media_images'): 2,    # ⑤⑥ 各一
}

# 允許「沒有自己的 preflight」的函式，逐條寫明理由。清單之外的每一個寫入點
# 所屬函式都必須自己呼叫 same_target_verdict。
_PREFLIGHT_EXEMPT = {
    ('core/organizer.py', 'organize_file'):
        '144-T0 的 `atomic_move(file_path, target_path)` 搬的是**影片本體**，不是封面或任何 '
        'stem 級衍生圖：`src` 是使用者的影片檔，`dest` 由番號/標題樣板算出（`format_string`），'
        '結構上不可能等於 `-poster`／`-fanart` 路徑。而且 `src != dest` 有雙重保證——外層的 '
        '`if file_path != target_path:` 與緊接在前的 `os.open(O_CREAT|O_EXCL)`（`dest` 是那一刻'
        '才被建立的 0 byte 佔位檔，必不等於已存在的 `src`）——所以 `same_target_verdict` 對這個'
        '呼叫點**恆為「不同檔」**，加上去只是一行永遠成立的廢話。'
        '⚠️ 這條例外只涵蓋「搬影片本體」這一個用途：任何**新的** `atomic_move` 呼叫點都會讓上面'
        '`_EXPECTED_WRITE_SITES` 的對帳轉紅，屆時必須重新判斷它需不需要 preflight，不得沿用本條。',
    ('core/organizer.py', 'crop_to_poster'):
        '葉節點函式：它的每一個呼叫端（②④⑥）都已在呼叫前 preflight，'
        '且它自身整段包在 try/except 裡，SameFileError 只會回 False、不會毀檔。',
}


def _scan(rel_path: str) -> dict:
    """{(檔案, 所屬函式, 被呼叫名稱): 次數}，涵蓋寫入呼叫與 preflight 呼叫。"""
    tree = ast.parse((REPO_ROOT / rel_path).read_text(encoding='utf-8'))
    found: dict = {}

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.stack: list = []

        def visit_FunctionDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_Call(self, node):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, 'id', None)
            if name in _WRITE_CALLS or name == _PREFLIGHT:
                key = (rel_path, '.'.join(self.stack), name)
                found[key] = found.get(key, 0) + 1
            self.generic_visit(node)

    Visitor().visit(tree)
    return found


def _all_calls() -> dict:
    merged: dict = {}
    for module in _MODULES:
        merged.update(_scan(module))
    return merged


class TestCoverWriteSiteInventory:
    def test_write_sites_match_hardcoded_inventory(self):
        """三個封面模組裡的每一個 copy2/copyfile/crop_to_poster 呼叫點，
        必須與硬編碼清單逐格相同（多一格、少一格、次數變了都轉紅）。"""
        actual = {k: v for k, v in _all_calls().items() if k[2] in _WRITE_CALLS}

        added = {k: v for k, v in actual.items() if k not in _EXPECTED_WRITE_SITES}
        removed = {k: v for k, v in _EXPECTED_WRITE_SITES.items() if k not in actual}
        changed = {
            k: (_EXPECTED_WRITE_SITES[k], v)
            for k, v in actual.items()
            if k in _EXPECTED_WRITE_SITES and _EXPECTED_WRITE_SITES[k] != v
        }

        assert not added, (
            f"新的封面/衍生圖寫入點：{sorted(added)}。\n"
            "先回 core/cover_layout.py 的「交棒清單」判斷它需不需要 "
            "same_target_verdict preflight（來源是不是 cover **不影響**判斷——"
            "判準是『有沒有寫到 stem 級衍生圖位置』），落檔後再把它加進本檔的 "
            "_EXPECTED_WRITE_SITES。"
        )
        assert not removed, (
            f"清單裡的寫入點已消失：{sorted(removed)}。刪除是好事，"
            "但要同步刪掉本檔與 core/cover_layout.py 交棒清單的對應列（反腐）。"
        )
        assert not changed, f"同一個函式裡的呼叫次數變了（預期, 實際）：{changed}"

    def test_every_write_site_owner_has_its_own_preflight(self):
        """每一個持有寫入呼叫的函式，都必須自己呼叫 same_target_verdict
        （葉節點例外逐條寫在 _PREFLIGHT_EXEMPT，附理由）。"""
        calls = _all_calls()
        owners = {(f, fn) for (f, fn, name) in calls if name in _WRITE_CALLS}
        with_preflight = {(f, fn) for (f, fn, name) in calls if name == _PREFLIGHT}

        unguarded = sorted(owners - with_preflight - set(_PREFLIGHT_EXEMPT))
        assert not unguarded, (
            f"這些函式直接寫封面/衍生圖但自己沒有 same_target_verdict preflight："
            f"{unguarded}。\n"
            "同檔情境下 shutil 會以 'wb' 開啟它正在讀的那個檔並清空它"
            "（`shutil.copyfile` 內部的 `_samefile` 把 OSError 吞成 False）——"
            "這正是 CD-112-8 存在的理由。"
        )

    def test_preflight_count_matches_write_site_count_per_owner(self):
        """Codex PR#125 round-3 P2：**逐 owner 對帳次數**，不是存在性。

        上一支只問「這個函式有沒有呼叫過 same_target_verdict」——一個函式裡有
        兩個寫入點時，拿掉其中一道保護、留著另一道，那支依然全綠。本支把
        「預期 preflight 次數」硬編碼，並要求它同時等於該 owner 的寫入點次數，
        所以任何一處寫圖少掉它自己那道保護都會轉紅。
        """
        calls = _all_calls()
        write_counts: dict = {}
        preflight_counts: dict = {}
        for (f, fn, name), n in calls.items():
            if name in _WRITE_CALLS:
                write_counts[(f, fn)] = write_counts.get((f, fn), 0) + n
            elif name == _PREFLIGHT:
                preflight_counts[(f, fn)] = preflight_counts.get((f, fn), 0) + n

        # ① 硬編碼清單 vs 實際 preflight 次數（BE-TEST-09：不由掃描結果反推）
        mismatched = {
            owner: (expected, preflight_counts.get(owner, 0))
            for owner, expected in _EXPECTED_PREFLIGHTS.items()
            if preflight_counts.get(owner, 0) != expected
        }
        assert not mismatched, (
            f"preflight 次數與硬編碼清單不符（預期, 實際）：{mismatched}。\n"
            "少一道＝某個寫入點失去它自己的同檔保護；多一道＝清單過期。"
        )
        undeclared = sorted(set(preflight_counts) - set(_EXPECTED_PREFLIGHTS))
        assert not undeclared, (
            f"這些函式呼叫了 same_target_verdict 但不在 _EXPECTED_PREFLIGHTS："
            f"{undeclared}。新增請補進清單並在 core/cover_layout.py 交棒清單落檔。"
        )

        # ② 每個非豁免 owner 的 preflight 次數必須等於它的寫入點次數
        short = {
            owner: (n_writes, preflight_counts.get(owner, 0))
            for owner, n_writes in write_counts.items()
            if owner not in _PREFLIGHT_EXEMPT and preflight_counts.get(owner, 0) != n_writes
        }
        assert not short, (
            f"寫入點數 != preflight 數（寫入, preflight）：{short}。\n"
            "每一個寫入點都要有它**自己**那一次 preflight——共用一次會讓另一個"
            "寫入點在同檔情境下裸奔（shutil 會清空它正在讀的那個檔）。"
        )

    def test_exempt_entries_are_not_stale(self):
        """反腐（照抄 py_function_size_lint 的 anti-rot 判準）：例外清單裡的
        每一條都必須仍然對應到一個真實存在、且真的沒有自己 preflight 的函式。"""
        calls = _all_calls()
        owners = {(f, fn) for (f, fn, name) in calls if name in _WRITE_CALLS}
        with_preflight = {(f, fn) for (f, fn, name) in calls if name == _PREFLIGHT}

        for entry in _PREFLIGHT_EXEMPT:
            assert entry in owners, f"例外清單條目已不存在（ghost）：{entry}"
            assert entry not in with_preflight, (
                f"例外清單條目現在已經自己 preflight 了（stale），請刪除：{entry}"
            )
