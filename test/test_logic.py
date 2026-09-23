#!/usr/bin/env python3
"""Offline tests for TOSGuard. No chain, no network, no model, no genlayer
install - stdlib only:

    python3 test/test_logic.py

What is under test:

 1. The URL rule: public HTTPS pages on named hosts only, normalised so two
    spellings of one page are one page.
 2. Normalisation (rule 8): case, whitespace, quotes and dashes never change a
    hash, a page that SHUFFLES its blocks between renders still yields one
    hash, and a changed clause always yields a new one.
 3. The clause scan: every flag's topic, explicit and denial vocabulary,
    matched at word starts, over synthetic terms AND real renders captured on
    Studio Dev (test/fixtures).
 4. The bracket (rule 7): what each evidence case allows, every open range
    exactly two wide, pinned cases never reach a model.
 5. The consensus gates, tested by BUILDING FORGERIES - one per field - and
    requiring each refused, and by moving each compared field in a validator's
    own reading and requiring disagreement.
 6. The contract: every refusal returns rather than raises and moves no
    counter, the cooldown, pending duplicates, batches, judging, stalls while
    paused, the per-flag summary, verify_check, and the value ledger.
 7. The source itself, walked as an AST: zero raises, no str.replace(), a
    two-line header, no undefined names, no `self` in a nondet closure.

The runtime stub below is ported from the AppAudit harness (itself from
GrantJudge, CourtRoom and WillExecutor); its TreeMap and DynArray reproduce the
runner's missing-key and append_new_get semantics exactly.
"""

import ast
import builtins
import json
import sys
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "contracts" / "TOSGuard.py"

GEN = 10 ** 18

_UNSET = object()


# ---------------------------------------------------------------------------
# runtime stub
#
# Ported from the proven CourtRoom/WillExecutor harness and kept on the v0.6 runner
# namespace: `gl.contract.Contract`, `gl.storage.TreeMap`, `gl.storage.DynArray`,
# `gl.storage.allow`, `gl.message.raw`, `gl.chain.Account`. A stub still shaped
# like an older namespace would let every test pass against a contract the
# current runner cannot even load.
#
# The TreeMap missing-key semantics in particular are load-bearing: on chain a
# map with a SCALAR value type answers a missing key with that type's ZERO, not
# with None, so a presence check written as `is not None` matches everything. A
# stub that returned None could never reproduce that bug.
# ---------------------------------------------------------------------------


class _UserError(Exception):
    def __init__(self, message: str = ""):
        super().__init__(message)
        self.message = message


class _Return:
    """gl.vm.Return - a leader result carrying its calldata."""

    def __init__(self, calldata):
        self.calldata = calldata


class _Rollback:
    def __init__(self, message=""):
        self.message = message


class _Addr:
    """Address. Compared and keyed by its lowercase text, like the real one, and
    carrying `.as_hex`, which is the ONLY spelling the runner guarantees. A stub
    whose `str()` happened to produce the hex would hide every place the
    contract forgot `.as_hex`."""

    def __init__(self, value=""):
        v = str(value)
        if not v.startswith("0x") or len(v) != 42:
            raise ValueError("not an address: " + v[:60])
        for ch in v[2:]:
            if ch not in "0123456789abcdefABCDEF":
                raise ValueError("not an address: " + v[:60])
        self._v = v.lower()

    @property
    def as_hex(self):
        return self._v

    def __str__(self):
        return self._v

    def __repr__(self):
        return "Address(" + self._v + ")"

    def __eq__(self, other):
        return isinstance(other, _Addr) and self._v == other._v

    def __hash__(self):
        return hash(self._v)


class _TreeMap(dict):
    """Models the runtime's TreeMap, INCLUDING what it returns for a key that is
    not there."""

    _value_type = None

    @classmethod
    def __class_getitem__(cls, item):
        vt = item[1] if isinstance(item, tuple) and len(item) > 1 else None
        return type("_TreeMapOf", (cls,), {"_value_type": vt})

    def _k(self, key):
        return str(key) if isinstance(key, _Addr) else key

    def _missing(self):
        vt = type(self)._value_type
        if vt is None:
            return None
        name = getattr(vt, "__name__", str(vt))
        if name.startswith("_TreeMap") or name.startswith("_DynArray"):
            return _zero_for(vt)
        if vt is int or vt is str or vt is bool:
            return _zero_for(vt)
        if hasattr(vt, "__annotations__") and getattr(vt, "__annotations__"):
            return None
        return _zero_for(vt)

    def get(self, key, default=_UNSET):
        k = self._k(key)
        if k in self:
            return dict.__getitem__(self, k)
        if default is not _UNSET:
            return default
        return self._missing()

    def __contains__(self, key):
        return dict.__contains__(self, self._k(key))

    def __setitem__(self, key, value):
        dict.__setitem__(self, self._k(key), value)

    def __getitem__(self, key):
        """Indexing a key the map does not hold RAISES KeyError, exactly as the
        runner does.

        This stub used to auto-create the entry instead, and that single line
        of convenience hid a real revert: `self.by_owner[sender].append(...)`
        passed 431 offline tests and then died on chain inside `create_will`,
        on the one path that had already banked a deposit. `get_or_insert_default`
        is the spelling that inserts. A stub that is more forgiving than the
        runner is a stub that certifies bugs."""
        return dict.__getitem__(self, self._k(key))

    def __delitem__(self, key):
        dict.__delitem__(self, self._k(key))

    def get_or_insert_default(self, key):
        k = self._k(key)
        if k not in self:
            dict.__setitem__(self, k, self._factory())
        return dict.__getitem__(self, k)

    def _factory(self):
        vt = type(self)._value_type
        if vt is None:
            return _DynArray()
        if hasattr(vt, "__annotations__") and getattr(vt, "__annotations__"):
            return _make_struct(vt)
        return _zero_for(vt)


class _DynArray(list):
    """Models DynArray, INCLUDING `append_new_get()`.

    On chain a DynArray of structs cannot be appended to with a constructed
    value, so the runtime allocates a zeroed element in place and hands back a
    REFERENCE to it. Reproducing that matters for more than API coverage: the
    returned object must be the SAME object the array holds, or a later
    mutation through the reference would be invisible in the array, and every
    test would pass while every will written on chain stayed zero."""

    _elem_type = None

    @classmethod
    def __class_getitem__(cls, item):
        return type("_DynArrayOf", (cls,), {"_elem_type": item})

    def append_new_get(self):
        elem = type(self)._elem_type
        value = _make_struct(elem) if elem is not None and \
            hasattr(elem, "__annotations__") else _zero_for(elem)
        list.append(self, value)
        return value


def _zero_for(annotation):
    """The value the runtime auto-initialises a storage field to."""
    name = getattr(annotation, "__name__", str(annotation))
    if annotation is bool or name == "bool":
        return False
    if annotation is str or name == "str":
        return ""
    if name == "_Addr" or name == "Address":
        return _Addr("0x" + "0" * 40)
    if name.startswith("_TreeMap") or name == "TreeMap":
        return annotation() if isinstance(annotation, type) else _TreeMap()
    if name.startswith("_DynArray") or name == "DynArray":
        return annotation() if isinstance(annotation, type) else _DynArray()
    if name.startswith("u") or name.startswith("i"):
        return 0
    if hasattr(annotation, "__annotations__"):
        return _make_struct(annotation)
    return 0


def _make_struct(cls):
    obj = cls.__new__(cls)
    for field, ann in getattr(cls, "__annotations__", {}).items():
        setattr(obj, field, _zero_for(ann))
    return obj


class _Contract:
    """gl.contract.Contract. Storage fields are declared as class annotations and
    never assigned before use, exactly as on chain, so they are created on
    demand."""

    balance = 0

    def __getattr__(self, name):
        anns = {}
        for klass in reversed(type(self).__mro__):
            anns.update(getattr(klass, "__annotations__", {}))
        if name in anns:
            value = _zero_for(anns[name])
            object.__setattr__(self, name, value)
            return value
        raise AttributeError(name)


TRANSFERS = []
BALANCES = {}
# address text -> contract instance, for cross-contract reads offline.
CONTRACTS = {}


class _Proxy:
    """gl.contract.Proxy. `.emit()` is a METHOD GETTER, exactly like the
    runner's, and it records NOTHING. That is the whole point: on chain,
    `emit()` with no method call after it constructs a namespace and drops it,
    posting no message. A stub that treated a bare `emit(value=...)` as a
    transfer would make this suite agree with a contract that silently never
    pays - which is precisely the bug that shipped once and had to be caught on
    chain by comparing real balances."""

    def __init__(self, address):
        self.address = address

    def view(self, **_k):
        """A cross-contract READ, routed to a contract this process is already
        holding.

        `CONTRACTS` is the offline stand-in for the chain's own register. It
        exists so that GrantConsumer can be driven against a REAL GrantJudge
        rather than against a mock of one - a consumer tested against a mock of
        the oracle is a consumer that has never been tested against the oracle's
        actual refusals, which are the whole of what it is for."""
        target = CONTRACTS.get(str(self.address))
        if target is None:
            raise RuntimeError("no contract at " + str(self.address))
        return target

    def emit(self, **_k):
        return None

    def emit_transfer(self, value, **_k):
        if int(value) <= 0:
            raise ValueError("value must be greater than 0 for emit_transfer")
        key = str(self.address)
        TRANSFERS.append((key, int(value)))
        BALANCES[key] = BALANCES.get(key, 0) + int(value)


class _Account:
    """gl.chain.Account - the wrapper the SDK documents for ANY on-chain
    account, contract or EOA.

    Its `emit_transfer` DELIVERS here. That is a deliberate difference from the
    network the contract is deployed on: Studio Dev queues an `on="finalized"`
    value transfer and never executes it, which is a property of that network
    and not of this contract. This suite models the INTENDED semantics so the
    money invariants can be proved end to end; `test/seed.mjs` asserts the other
    half on chain - that the call posts a well-formed queued transfer to the
    right address for the right amount. Neither check is sufficient alone."""

    def __init__(self, address):
        self.address = address

    @property
    def balance(self):
        return BALANCES.get(str(self.address), 0)

    def emit_transfer(self, value, **_k):
        if int(value) <= 0:
            raise ValueError("value must be greater than 0 for emit_transfer")
        key = str(self.address)
        TRANSFERS.append((key, int(value)))
        BALANCES[key] = BALANCES.get(key, 0) + int(value)


def _proxy_for(address):
    return _Proxy(address)


def _contract_interface(cls):
    return _proxy_for


def _evm_contract_interface(cls):
    class _Handle:
        def __init__(self, to):
            self.to = to
    return _Handle


MESSAGE = types.SimpleNamespace(sender_address=_Addr("0x" + "a" * 40), value=0,
                                raw={"datetime": "2026-09-18T12:00:00Z"})

# ---------------------------------------------------------------------------
# the scorer stub
#
# `_collect` is called TWICE per consensus round offline - once by the leader
# and once by the validator - so the default mode is STICKY: one queued answer
# serves every call until it is replaced. `script()` exists for the opposite
# case, where the leader and the validator must be made to see different things
# in order to prove that disagreement settles nothing.
#
# It answers with a DICT, because the contract asks for `response_format="json"`
# and the runner hands back a decoded object rather than a string. A stub that
# returned a string would let the contract's JSON parser be tested against a
# shape the runner never produces.
# ---------------------------------------------------------------------------


class _Model:
    """The model stub. STICKY by default - one answer serves leader and
    validator alike - with `script()` for rounds where the two must differ.
    Answers are DICTS, because the contract asks for response_format="json"
    and the runner hands back a decoded object."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.sticky = None
        self.queue = []
        self.log = []
        self.raise_next = 0
        self.calls = 0

    def serve(self, outcome, clarity, scope):
        self.sticky = {"outcome": outcome, "clarity_bucket": clarity,
                       "scope_bucket": scope}
        self.queue = []

    def serve_raw(self, payload):
        self.sticky = payload
        self.queue = []

    def script(self, *answers):
        out = []
        for item in answers:
            if isinstance(item, tuple):
                out.append({"outcome": item[0], "clarity_bucket": item[1],
                            "scope_bucket": item[2]})
            else:
                out.append(item)
        self.queue = out

    def fail(self, times=1):
        self.raise_next = times

    def _next(self, prompt):
        self.calls += 1
        self.log.append(prompt)
        if self.raise_next > 0:
            self.raise_next -= 1
            raise RuntimeError("the model endpoint refused the connection")
        if self.queue:
            return self.queue.pop(0)
        if self.sticky is None:
            raise AssertionError("model call with no queued answer")
        return self.sticky


MODEL = _Model()


def _exec_prompt(prompt, **kwargs):
    if kwargs.get("response_format") != "json":
        raise AssertionError("TOSGuard must ask for response_format='json'")
    return MODEL._next(prompt)


class _Web:
    """The render stub. Pages are keyed by URL; `down` makes a URL raise the way
    render() does on a non-2xx; `script()` queues different pages for
    successive renders (leader first, then validator) to model a listing that
    changes between two nodes' fetches."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.pages = {}
        self.queue = {}
        self.down = set()
        self.calls = []

    def serve(self, url, text):
        self.pages[url] = text

    def script(self, url, *texts):
        self.queue[url] = list(texts)

    def render(self, url, mode="text", **_k):
        self.calls.append((url, mode))
        if mode != "text":
            raise AssertionError("TOSGuard must render in text mode")
        if url in self.down:
            raise RuntimeError("WEBPAGE_LOAD_FAILED 503")
        q = self.queue.get(url)
        if q:
            return q.pop(0)
        if url not in self.pages:
            raise RuntimeError("WEBPAGE_LOAD_FAILED 404 (no fixture for " + url + ")")
        return self.pages[url]


WEB = _Web()


def _web_get_forbidden(*_a, **_k):
    raise AssertionError("TOSGuard must render, never GET")


LAST_CONSENSUS = {}

# Set by a test to make the leader misbehave. Kept OUT of LAST_CONSENSUS
# because that dict is cleared at the top of every round - a forgery stored
# there would be wiped before it could be used, and the test would silently
# assert nothing.
FORGE = {"payload": None, "leader_dies": False}


def _run_nondet(leader_fn, validator_fn):
    """Runs the real consensus shape offline: the leader produces a result, a
    validator is handed it as gl.vm.Return and must agree, and disagreement is
    surfaced the way the chain surfaces it - as a round that returns nothing.

    The validator runs the SAME closure the contract gave it, so a validator
    that re-scores really does re-score here too."""
    LAST_CONSENSUS.clear()
    if FORGE["leader_dies"]:
        # A round that never settled. On chain the transaction goes
        # UNDETERMINED and NO state is applied at all; here the call simply
        # answers nothing, which is what the contract must survive.
        LAST_CONSENSUS["agreed"] = False
        return None
    try:
        result = leader_fn()
    except Exception as e:
        LAST_CONSENSUS["agreed"] = False
        LAST_CONSENSUS["leader_error"] = str(e)
        return None
    LAST_CONSENSUS["leader"] = result
    if FORGE["payload"] is not None:
        result = FORGE["payload"]
    agreed = validator_fn(_Return(result))
    LAST_CONSENSUS["agreed"] = bool(agreed)
    if not agreed:
        return None
    return result


def _install_stub():
    if "genlayer" in sys.modules:
        return
    mod = types.ModuleType("genlayer")
    vm = types.SimpleNamespace(UserError=_UserError, Return=_Return,
                               Result=object, Rollback=_Rollback,
                               run_nondet=_run_nondet,
                               run_nondet_unsafe=_run_nondet)
    web = types.SimpleNamespace(request=_web_get_forbidden,
                                render=WEB.render,
                                get=_web_get_forbidden)
    nondet = types.SimpleNamespace(web=web, exec_prompt=_exec_prompt)
    public = types.SimpleNamespace()
    public.view = lambda fn: fn
    write = lambda fn: fn
    write.payable = lambda fn: fn
    public.write = write
    evm = types.SimpleNamespace(contract_interface=_evm_contract_interface)
    storage = types.SimpleNamespace(TreeMap=_TreeMap, DynArray=_DynArray,
                                    allow=lambda cls: cls)
    contract_ns = types.SimpleNamespace(Contract=_Contract,
                                        get_at=lambda a: _proxy_for(a),
                                        interface=_contract_interface)
    chain_ns = types.SimpleNamespace(Account=_Account, id=61997)
    mod.gl = types.SimpleNamespace(vm=vm, nondet=nondet, public=public, evm=evm,
                                   storage=storage, message=MESSAGE,
                                   contract=contract_ns, chain=chain_ns)
    mod.Address = _Addr
    mod.TreeMap = _TreeMap
    mod.DynArray = _DynArray
    for name in ("u8", "u16", "u32", "u64", "u128", "u256", "i8", "i16", "i32",
                 "i64", "bigint"):
        mod.__dict__[name] = int
    sys.modules["genlayer"] = mod
    sys.modules["genlayer.gl"] = mod.gl


def load_pure(path: Path, name: str) -> types.ModuleType:
    """Exec only the pure region - every top-level statement before the first
    class definition. That region never touches storage."""
    tree = ast.parse(path.read_text(encoding="utf8"))
    cut = len(tree.body)
    for i, node in enumerate(tree.body):
        if isinstance(node, ast.ClassDef):
            cut = i
            break
    tree.body = tree.body[:cut]
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(tree, str(path), "exec"), module.__dict__)
    return module


def load_full(path: Path, name: str) -> types.ModuleType:
    """Exec the WHOLE file so the contract class itself can be driven."""
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(path.read_text(encoding="utf8"), str(path), "exec"),
         module.__dict__)
    return module



# ---------------------------------------------------------------------------

def _own_nodes(scope):
    out = []

    def rec(node):
        for sub in ast.iter_child_nodes(node):
            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef,
                                ast.Lambda)):
                continue
            out.append(sub)
            rec(sub)
    rec(scope)
    return out


def _child_scopes(scope):
    out = []

    def rec(node):
        for sub in ast.iter_child_nodes(node):
            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef,
                                ast.Lambda)):
                out.append(sub)
            else:
                rec(sub)
    rec(scope)
    return out


def _bound_names(scope) -> set:
    out = set()
    args = getattr(scope, "args", None)
    if args is not None:
        for group in (args.posonlyargs, args.args, args.kwonlyargs):
            for a in group:
                out.add(a.arg)
        if args.vararg:
            out.add(args.vararg.arg)
        if args.kwarg:
            out.add(args.kwarg.arg)
    for sub in _own_nodes(scope):
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
            out.add(sub.id)
        elif isinstance(sub, ast.ExceptHandler) and sub.name:
            out.add(sub.name)
        elif isinstance(sub, (ast.Global, ast.Nonlocal)):
            out.update(sub.names)
        elif isinstance(sub, (ast.Import, ast.ImportFrom)):
            for al in sub.names:
                out.add((al.asname or al.name).split(".")[0])
        elif isinstance(sub, ast.comprehension):
            for nm in ast.walk(sub.target):
                if isinstance(nm, ast.Name):
                    out.add(nm.id)
    for sub in _child_scopes(scope):
        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.add(sub.name)
    for sub in _own_nodes(scope):
        if isinstance(sub, ast.ClassDef):
            out.add(sub.name)
    return out


def undefined_names(path: Path) -> list:
    tree = ast.parse(path.read_text(encoding="utf8"))
    module_names = _bound_names(tree) | {
        "gl", "u8", "u16", "u32", "u64", "u128", "u256", "i8", "i16", "i32",
        "i64", "Address", "TreeMap", "DynArray", "bigint", "Array", "self"}
    builtin_names = set(dir(builtins))
    problems = []

    def visit(scope, enclosing, label):
        scope_names = enclosing | _bound_names(scope)
        for sub in _own_nodes(scope):
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                if sub.id not in scope_names and sub.id not in builtin_names:
                    problems.append((label, sub.id, sub.lineno))
        for child in _child_scopes(scope):
            visit(child, scope_names,
                  label + "." + getattr(child, "name", "<lambda>"))

    for child in _child_scopes(tree):
        visit(child, module_names, getattr(child, "name", "<lambda>"))
    for node in _own_nodes(tree):
        if isinstance(node, ast.ClassDef):
            for child in _child_scopes(node):
                visit(child, module_names | _bound_names(node),
                      node.name + "." + getattr(child, "name", "<lambda>"))
    return problems




# ---------------------------------------------------------------------------
# module loading and shared fixtures
# ---------------------------------------------------------------------------

_install_stub()

P = load_pure(SOURCE, "tosguard_pure")
MOD = load_full(SOURCE, "tosguard_full")
TREE = ast.parse(SOURCE.read_text(encoding="utf8"))
SRC_TEXT = SOURCE.read_text(encoding="utf8")

NOW_ISO = "2026-09-23T12:00:00Z"
NOW = P._epoch_from_iso(NOW_ISO)

OWNER = _Addr("0x" + "a" * 40)
ALICE = _Addr("0x" + "b" * 40)
BOB = _Addr("0x" + "c" * 40)
CAROL = _Addr("0x" + "d" * 40)
STRANGER = _Addr("0x" + "1" * 40)


def iso(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def set_now(ts: int) -> None:
    MESSAGE.raw["datetime"] = iso(ts)


FIXTURES = ROOT / "test" / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf8")


# --- synthetic terms ---------------------------------------------------------
#
# A header carrying legal markers that are NOT topic words of any flag, and
# neutral filler that matches nothing, so each test controls exactly which
# clauses a page contains.

HEADER = ("TERMS OF SERVICE\n"
          "These Terms of Service form a binding contract. By using the "
          "website you agree to these terms.\n"
          "This agreement is subject to the governing law of the State of "
          "Delaware and the jurisdiction of its courts.\n"
          "Please also read our privacy policy.\n")


def filler(n: int) -> str:
    out = []
    for i in range(n):
        out.append("Clause " + str(i) + ". Please read each section of this "
                   "document carefully and keep a copy for your records.")
    return "\n".join(out)


def tos(*clauses, pad: int = 80) -> str:
    """A legal document of roughly 100 * pad characters with `clauses`."""
    body = [HEADER]
    half = pad // 2
    body.append(filler(half))
    for c in clauses:
        body.append(c)
    body.append(filler(pad - half))
    return "\n".join(body)


SALE = "We may sell your personal information to data brokers and advertisers."
SALE2 = "We share your personal data with third parties for marketing."
NO_SALE = "We do not sell your personal information to anyone."
NO_SALE2 = "DuckDuckGo does not share personal information with advertisers."
SALE3 = ("We may disclose your personal information to third parties for "
         "advertising.")
NO_SALE3 = "We will not sell or rent your personal information to data brokers."
SALE4 = ("We share data with our advertising partners to show personalized "
         "ads, and we may monetize your data.")
# A STRONG DATA_SALE page: seven distinct indicators (sell, share, third
# party, partner, monetize, personalized ads, data broker).
RED3 = (SALE, SALE2, SALE3, SALE4)
# A MODERATE page that leans CLEAN: three denials against one clause that hits
# two indicators (share, partner).
DENY_SIGNAL = "We share data with our advertising partners only in aggregate."
DENY3 = (NO_SALE, NO_SALE2, NO_SALE3, DENY_SIGNAL)
LICENSE = ("You grant us a worldwide, royalty-free, perpetual, irrevocable and "
           "sublicensable license to use your content.")
RETAIN = "You retain ownership of your content and we do not claim ownership."
RENEW = ("Your subscription will automatically renew each month unless you "
         "cancel at least 24 hours before the end of the period.")
ARB = ("You and the Company agree to resolve any dispute by binding "
       "arbitration and waive the right to a class action.")
CHANGE = ("We may modify these terms at any time without notice and your "
          "continued use means you accept them.")
TERMINATE = ("We may suspend or terminate your account at any time for any "
             "reason or no reason without notice.")
LIABLE = ("IN NO EVENT SHALL THE COMPANY BE LIABLE FOR ANY INDIRECT, INCIDENTAL "
          "OR CONSEQUENTIAL DAMAGES ARISING FROM YOUR USE OF THE SERVICE.")

URL = "https://example-service.com/terms"
URL2 = "https://another-service.org/legal/tos"
NOT_TOS_PAGE = ("Example Domain\nThis domain is for use in illustrative examples "
                "in documents. You may use this domain in literature without "
                "prior coordination or asking for permission.\nMore "
                "information...\n" + filler(20))


def fresh(**kwargs):
    TRANSFERS.clear()
    BALANCES.clear()
    MODEL.reset()
    WEB.reset()
    FORGE["payload"] = None
    FORGE["leader_dies"] = False
    LAST_CONSENSUS.clear()
    MESSAGE.sender_address = OWNER
    MESSAGE.value = 0
    set_now(NOW)
    return MOD.TOSGuard(**kwargs)


def send(c, who, method, *args, value=0):
    MESSAGE.sender_address = who
    MESSAGE.value = value
    try:
        return getattr(c, method)(*args)
    finally:
        MESSAGE.value = 0


def ok(out) -> bool:
    return isinstance(out, dict) and out.get("status") == "OK"


def rejected(out) -> bool:
    return isinstance(out, dict) and out.get("status") == "REJECTED"


def facts(url=URL, flag="DATA_SALE", concern="", cid=1):
    return {"check_id": cid, "url": url, "flag_type": flag, "concern": concern}


def ev_of(page, flag="DATA_SALE", rendered=True):
    return P._read_page(page, rendered, flag)


def br_of(page, flag="DATA_SALE"):
    return P._bracket(flag, ev_of(page, flag))


def honest(f, page, outcome=None, clarity=None, scope=None):
    """What an honest node returns for page `page`."""
    ev = ev_of(page, f["flag_type"])
    br = P._bracket(f["flag_type"], ev)
    o = outcome if outcome is not None else br["allowed"][0]
    c = clarity if clarity is not None else br["clarity"][o][0]
    s = scope if scope is not None else br["scope"][o][0]
    return P._ok(P._derive(f, ev, o, c, s))


def submit(c, who=ALICE, url=URL, flag="DATA_SALE", concern=""):
    return send(c, who, "check_tos", url, flag, concern)


def judge(c, cid, page=None, url=URL, answer=None, who=STRANGER):
    if page is not None:
        WEB.serve(url, page)
    if answer is not None:
        MODEL.serve(*answer)
    return send(c, who, "judge_check", cid)


# ---------------------------------------------------------------------------
# 1. helpers
# ---------------------------------------------------------------------------


class TestHelpers(unittest.TestCase):
    def test_as_int_rejects_bool(self):
        self.assertEqual(P._as_int(True, 7), 7)

    def test_as_int_parses_strings(self):
        self.assertEqual(P._as_int(" 42 "), 42)
        self.assertEqual(P._as_int("-3"), -3)
        self.assertEqual(P._as_int("4x", 9), 9)

    def test_as_int_float_and_junk(self):
        self.assertEqual(P._as_int(3.9), 3)
        self.assertEqual(P._as_int(None, 5), 5)

    def test_clamp(self):
        self.assertEqual(P._clamp(-1, 0, 7), 0)
        self.assertEqual(P._clamp(9, 0, 7), 7)
        self.assertEqual(P._clamp(4, 0, 7), 4)

    def test_rank_ladder(self):
        self.assertEqual(P._rank(0, P.LENGTH_LADDER), 0)
        self.assertEqual(P._rank(1000, P.LENGTH_LADDER), 1)
        self.assertEqual(P._rank(10 ** 6, P.LENGTH_LADDER), 7)

    def test_length_ladder_tops_at_seven(self):
        self.assertEqual(len(P.LENGTH_LADDER), P.TOP_BUCKET)

    def test_fnv_known_vector(self):
        # FNV-1a 64 of the empty string is the offset basis.
        self.assertEqual(P._fnv(""), "cbf29ce484222325")
        self.assertEqual(P._fnv("a"), "af63dc4c8601ec8c")

    def test_epoch(self):
        self.assertEqual(P._epoch_from_iso("1970-01-01T00:00:00Z"), 0)
        self.assertEqual(P._epoch_from_iso("2000-03-01T00:00:00Z"), 951868800)
        self.assertEqual(P._epoch_from_iso("junk"), 0)
        self.assertEqual(P._epoch_from_iso("2026-13-01T00:00:00Z"), 0)

    def test_epoch_matches_datetime(self):
        for ts in (0, 86399, 951868800, NOW, NOW + 12345678):
            self.assertEqual(P._epoch_from_iso(iso(ts)), ts)

    def test_is_addr(self):
        self.assertTrue(P._is_addr("0x" + "a" * 40))
        self.assertFalse(P._is_addr("0x" + "g" * 40))
        self.assertFalse(P._is_addr("0x123"))

    def test_clean_strips_control_and_bidi(self):
        self.assertEqual(P._clean("a‮b​c\x00d", 50), "abcd")

    def test_clean_caps(self):
        self.assertEqual(len(P._clean("x" * 500, 10)), 10)

    def test_err_text_prefers_data(self):
        e = types.SimpleNamespace(data="boom", message="")
        self.assertEqual(P._err_text(e), "boom")

    def test_flag_lookup_case_insensitive(self):
        self.assertEqual(P._flag(" data_sale ")[0], "DATA_SALE")
        self.assertIsNone(P._flag("DATA SALE"))

    def test_vocabulary_is_seven_closed_flags(self):
        self.assertEqual(P.FLAG_KEYS, ("DATA_SALE", "CONTENT_OWNERSHIP",
                                       "AUTO_RENEWAL", "MANDATORY_ARBITRATION",
                                       "UNILATERAL_CHANGE",
                                       "ACCOUNT_TERMINATION",
                                       "LIABILITY_WAIVER"))

    def test_every_phrase_is_lower_case(self):
        for f in P.FLAGS:
            phrases = list(f[6]) + list(f[7])
            for group in f[4]:
                phrases.extend(group)
            for name, patterns in f[5]:
                phrases.append(name)
                phrases.extend(patterns)
            for p in phrases:
                self.assertEqual(p, p.lower(), f[0] + ": " + p)
        for p in P.BROAD_WORDS + P.LEGAL_MARKERS:
            self.assertEqual(p, p.lower())

    def test_indicator_families_match_the_brief(self):
        want = {
            "DATA_SALE": ["sell", "share", "third party", "partner",
                          "advertiser", "marketing", "monetize",
                          "personalized ads", "data broker", "affiliate"],
            "CONTENT_OWNERSHIP": ["license", "perpetual", "irrevocable",
                                  "sublicense", "royalty-free", "worldwide",
                                  "reproduce", "derivative", "grant us"],
            "AUTO_RENEWAL": ["auto-renew", "automatically renew", "recurring",
                             "cancel before", "billing cycle", "continuous"],
            "MANDATORY_ARBITRATION": ["arbitration", "waive", "class action",
                                      "individual basis",
                                      "dispute resolution",
                                      "binding arbitration"],
            "UNILATERAL_CHANGE": ["modify these terms", "change at any time",
                                  "sole discretion", "without notice",
                                  "revised terms",
                                  "continued use constitutes"],
            "ACCOUNT_TERMINATION": ["terminate", "suspend", "disable",
                                    "any reason", "sole discretion",
                                    "without notice", "right to remove"],
            "LIABILITY_WAIVER": ["not liable", "no warranty", "as is",
                                 "limitation of liability",
                                 "consequential damages", "indemnify"],
        }
        for f in P.FLAGS:
            self.assertEqual([n for n, _ in f[5]], want[f[0]], f[0])

    def test_no_brand_names_in_the_vocabulary(self):
        for f in P.FLAGS:
            for _n, patterns in f[5]:
                for p in patterns:
                    for brand in ("discord", "github", "zoom", "twitter",
                                  "duckduckgo", "reddit"):
                        self.assertNotIn(brand, p)

    def test_base_severities_leave_room_for_broad(self):
        for f in P.FLAGS:
            self.assertTrue(1 <= f[3] <= 6, f[0])


# ---------------------------------------------------------------------------
# 2. URLs
# ---------------------------------------------------------------------------

GOOD_URLS = [
    ("https://twitter.com/en/tos", "https://twitter.com/en/tos"),
    ("https://www.reddit.com/policies/user-agreement",
     "https://www.reddit.com/policies/user-agreement"),
    ("https://duckduckgo.com/terms", "https://duckduckgo.com/terms"),
    ("https://www.wikipedia.org/wiki/Terms_of_Use",
     "https://www.wikipedia.org/wiki/Terms_of_Use"),
    ("HTTPS://DuckDuckGo.COM/terms", "https://duckduckgo.com/terms"),
    ("https://example.com", "https://example.com/"),
    ("https://example.com?lang=en", "https://example.com/?lang=en"),
    ("https://example.com/terms#section-4", "https://example.com/terms"),
    ("  https://example.com/terms  ", "https://example.com/terms"),
    ("https://example.com./terms", "https://example.com/terms"),
    ("https://sub.domain.co.uk/legal/Terms", "https://sub.domain.co.uk/legal/Terms"),
    ("https://a-b.io/t?x=1&y=2", "https://a-b.io/t?x=1&y=2"),
    ("https://policies.google.com/terms?hl=en",
     "https://policies.google.com/terms?hl=en"),
    ("https://xn--bcher-kva.example.com/tos", "https://xn--bcher-kva.example.com/tos"),
]

BAD_URLS = [
    "", "http://example.com/terms", "ftp://example.com/terms",
    "example.com/terms", "https://", "https:///terms",
    "https://localhost/terms", "https://127.0.0.1/terms",
    "https://10.0.0.8/tos", "https://192.168.1.1/", "https://[::1]/",
    "https://example.com:8443/terms", "https://user:pass@example.com/",
    "https://user@example.com/", "https://intranet/terms",
    "https://studio-webdriver:4444/render", "https://printer.local/",
    "https://svc.internal/tos", "https://metadata.google.internal/",
    "https://exa mple.com/", "https://example.com/te rms",
    "https://example.com/\"onload", "https://-bad.com/",
    "https://bad-.com/", "https://a..b.com/", "https://.example.com/",
    "https://example.c/", "https://example.123/",
    "https://example.com/" + "a" * 300, "https://exämple.com/",
    "javascript:alert(1)", "https://example.com/\nx",
]


class TestUrls(unittest.TestCase):
    pass


def _make_good(i, row):
    raw, want = row

    def t(self):
        got = P._parse_url(raw)
        self.assertTrue(got["ok"], raw + " -> " + got.get("error", ""))
        self.assertEqual(got["url"], want)
    t.__name__ = "test_good_url_%02d" % i
    return t


def _make_bad(i, raw):
    def t(self):
        got = P._parse_url(raw)
        self.assertFalse(got["ok"], raw)
        self.assertTrue(got["error"])
    t.__name__ = "test_bad_url_%02d" % i
    return t


for _i, _row in enumerate(GOOD_URLS):
    setattr(TestUrls, "test_good_url_%02d" % _i, _make_good(_i, _row))
for _i, _raw in enumerate(BAD_URLS):
    setattr(TestUrls, "test_bad_url_%02d" % _i, _make_bad(_i, _raw))


class TestUrlRules(unittest.TestCase):
    def test_none_is_refused(self):
        self.assertFalse(P._parse_url(None)["ok"])

    def test_host_is_reported_lower(self):
        self.assertEqual(P._parse_url("https://WWW.Reddit.com/x")["host"],
                         "www.reddit.com")

    def test_path_case_is_kept(self):
        self.assertTrue(P._parse_url("https://a.com/Terms")["url"]
                        .endswith("/Terms"))

    def test_fragment_never_reaches_storage(self):
        self.assertNotIn("#", P._parse_url("https://a.com/t#x")["url"])


# ---------------------------------------------------------------------------
# 3. normalisation and the shuffle lesson
# ---------------------------------------------------------------------------


class TestNormalisation(unittest.TestCase):
    def test_lower_and_collapse(self):
        self.assertEqual(P._norm("  We   MAY\tSell \n Data "), "we may sell data")

    def test_quotes_and_dashes_unified(self):
        self.assertEqual(P._norm("“AS IS” — don’t"),
                         "\"as is\" - don't")

    def test_nbsp_and_zero_width(self):
        self.assertEqual(P._norm("sell your​ data"), "sell your data")

    def test_soft_hyphen_dropped(self):
        self.assertEqual(P._norm("arbi­tration"), "arbitration")

    def test_sentence_split_on_terminators(self):
        got = P._split_sentences("One. Two? Three! Four")
        self.assertEqual(got, ["One.", "Two?", "Three!", "Four"])

    def test_sentence_split_keeps_decimals(self):
        self.assertEqual(P._split_sentences("Fee is 1.5 GEN. Next"),
                         ["Fee is 1.5 GEN.", "Next"])

    def test_sentence_split_on_newlines_and_cr(self):
        self.assertEqual(P._split_sentences("a line\r\nb line"),
                         ["a line", "b line"])

    def test_giant_line_is_chunked(self):
        got = P._split_sentences("x" * 5000)
        self.assertTrue(len(got) >= 6)
        for s in got:
            self.assertTrue(len(s) <= P.MAX_SENTENCE * 2)

    def test_case_and_whitespace_do_not_change_hash(self):
        a = ev_of(tos(SALE))
        b = ev_of(tos(SALE.upper().replace(" ", "   ")))
        self.assertEqual(a["excerpt"], b["excerpt"])
        self.assertEqual(P._content_hash(URL, "DATA_SALE", a["excerpt"]),
                         P._content_hash(URL, "DATA_SALE", b["excerpt"]))

    def test_shuffled_blocks_hash_identically(self):
        a = ev_of(tos(SALE, NO_SALE, SALE2, pad=60))
        b = ev_of(tos(SALE2, SALE, NO_SALE, pad=60))
        self.assertEqual(a["excerpt"], b["excerpt"])
        self.assertEqual(a["matched_total"], b["matched_total"])

    def test_curly_quote_variant_hashes_identically(self):
        a = ev_of(tos("We don't sell your personal information."))
        b = ev_of(tos("We don’t sell your personal information."))
        self.assertEqual(a["excerpt"], b["excerpt"])

    def test_duplicate_clause_counted_once(self):
        a = ev_of(tos(SALE, SALE, SALE))
        self.assertEqual(a["matched_total"], 1)

    def test_changed_clause_changes_hash(self):
        a = ev_of(tos(SALE))
        b = ev_of(tos(SALE[:-1] + " and partners."))
        self.assertNotEqual(P._content_hash(URL, "DATA_SALE", a["excerpt"]),
                            P._content_hash(URL, "DATA_SALE", b["excerpt"]))

    def test_irrelevant_noise_does_not_change_hash(self):
        a = ev_of(tos(SALE, pad=60))
        b = ev_of(tos(SALE, "Trending now: 12,345 posts about the weather.",
                      pad=61))
        self.assertEqual(a["excerpt"], b["excerpt"])

    def test_hash_binds_url_and_flag(self):
        e = ev_of(tos(SALE))["excerpt"]
        h = P._content_hash(URL, "DATA_SALE", e)
        self.assertNotEqual(h, P._content_hash(URL2, "DATA_SALE", e))
        self.assertNotEqual(h, P._content_hash(URL, "AUTO_RENEWAL", e))

    def test_excerpt_is_sorted(self):
        lines = ev_of(tos(SALE2, NO_SALE, SALE))["excerpt"].split("\n")
        self.assertEqual(lines, sorted(lines))

    def test_excerpt_bounded(self):
        many = []
        for i in range(200):
            many.append("We share your personal data with partner number "
                        + str(i) + " for advertising purposes and analytics.")
        e = ev_of(tos(*many))
        self.assertTrue(len(e["excerpt"]) <= P.MAX_EXCERPT)
        self.assertTrue(len(e["excerpt"].split("\n"))
                        <= P.MAX_EXCERPT_SENTENCES)
        self.assertEqual(e["matched_total"], 200)

    def test_explicit_clauses_survive_the_cap(self):
        many = []
        for i in range(60):
            many.append("Our partner program number " + str(i)
                        + " is described on the help pages.")
        e = ev_of(tos(SALE, *many))
        self.assertIn(P._norm(SALE), e["excerpt"])


# ---------------------------------------------------------------------------
# 4. the clause scan
# ---------------------------------------------------------------------------

HAS_CASES = [
    ("we may sell data", "sell", True),
    ("we are selling data", "sell", True),
    ("seek legal counsel", "sell", False),
    ("upsell offers", "sell", False),
    ("the arbitration clause", "arbitrat", True),
    ("sharing is caring", "share", False),
    ("shareholders meet", "share", True),
    ("banking partners", "banned", False),
    ("x", "", True),
    ("(sell) your", "sell", True),
    ("presell", "sell", False),
    ("self-sell", "sell", True),
]


class TestHas(unittest.TestCase):
    pass


def _make_has(i, row):
    s, p, want = row

    def t(self):
        self.assertEqual(P._has(s, p), want, repr(row))
    t.__name__ = "test_has_%02d" % i
    return t


for _i, _row in enumerate(HAS_CASES):
    setattr(TestHas, "test_has_%02d" % _i, _make_has(_i, _row))

CLASSIFY_CASES = [
    ("DATA_SALE", SALE, "signal"),
    ("DATA_SALE", SALE2, "signal"),
    ("DATA_SALE", SALE4, "signal"),
    ("DATA_SALE", NO_SALE, "denied"),
    ("DATA_SALE", NO_SALE2, "denied"),
    ("DATA_SALE", NO_SALE3, "denied"),
    ("DATA_SALE", "We never sell or rent personal information.", "denied"),
    ("DATA_SALE", "We do not sell your data, but we share your data with "
                  "third parties.", "signal"),
    ("DATA_SALE", "You may not share an account with any other individual.",
     ""),
    ("DATA_SALE", "The software may be used in connection with third party "
                  "offerings.", ""),
    ("DATA_SALE", "Please seek legal counsel.", ""),
    ("DATA_SALE", "We show personalized ads based on your activity.",
     "signal"),
    ("CONTENT_OWNERSHIP", LICENSE, "signal"),
    ("CONTENT_OWNERSHIP", RETAIN, "denied"),
    ("CONTENT_OWNERSHIP", "You retain ownership of your content, but you "
                          "grant us a worldwide license to it.", "signal"),
    ("CONTENT_OWNERSHIP", "Our perpetual calendar is available worldwide.",
     ""),
    ("CONTENT_OWNERSHIP", "By sending us feedback, you grant us a perpetual, "
                          "irrevocable license to use it.", ""),
    ("CONTENT_OWNERSHIP", "We give you a personal, worldwide, royalty-free "
                          "license to use the software.", ""),
    ("AUTO_RENEWAL", RENEW, "signal"),
    ("AUTO_RENEWAL", "Subscriptions do not renew; you pay once.", "denied"),
    ("AUTO_RENEWAL", "You can cancel from the settings page.", ""),
    ("MANDATORY_ARBITRATION", ARB, "signal"),
    ("MANDATORY_ARBITRATION", "This agreement does not require arbitration "
                              "of disputes.", "denied"),
    ("MANDATORY_ARBITRATION", "Small claims court remains available.", ""),
    ("UNILATERAL_CHANGE", CHANGE, "signal"),
    ("UNILATERAL_CHANGE", "We will notify you in advance of changes to "
                          "these terms.", "denied"),
    ("UNILATERAL_CHANGE", "You may cancel at any time.", ""),
    ("UNILATERAL_CHANGE", "We may delete any content at any time without "
                          "notice if it violates this agreement.", ""),
    ("UNILATERAL_CHANGE", "If you continue to use the services after the "
                          "changes, you agree to the revised terms.",
     "signal"),
    ("ACCOUNT_TERMINATION", TERMINATE, "signal"),
    ("ACCOUNT_TERMINATION", "We terminate accounts only for cause after a "
                            "review.", "denied"),
    ("ACCOUNT_TERMINATION", "Contact support for anything else.", ""),
    ("LIABILITY_WAIVER", LIABLE, "signal"),
    ("LIABILITY_WAIVER", "The service is provided \"as is\" without "
                         "warranties.", "signal"),
    ("LIABILITY_WAIVER", "Hello world.", ""),
]


class TestClassify(unittest.TestCase):
    pass


def _make_classify(i, row):
    flag, sentence, want = row

    def t(self):
        got = P._classify(P._norm(sentence), P._flag(flag))
        self.assertEqual(got, want, flag + ": " + sentence)
    t.__name__ = "test_classify_%02d" % i
    return t


for _i, _row in enumerate(CLASSIFY_CASES):
    setattr(TestClassify, "test_classify_%02d" % _i, _make_classify(_i, _row))


class TestCut(unittest.TestCase):
    def test_cut_removes_word_start_phrase_and_its_clause(self):
        self.assertEqual(" ".join(P._cut("we do not sell data", ("not sell",))
                                  .split()), "we do")

    def test_cut_stops_at_clause_break(self):
        got = P._cut("we do not sell data, but we share it", ("not sell",))
        self.assertIn("but we share it", got)
        self.assertNotIn("data", got)

    def test_cut_keeps_mid_word(self):
        self.assertEqual(P._cut("cannot sell", ("not sell",)), "cannot sell")

    def test_cut_every_occurrence(self):
        got = P._cut("not sell a, not sell b", ("not sell",))
        self.assertNotIn("not sell", got)

    def test_cut_empty_phrase_is_noop(self):
        self.assertEqual(P._cut("abc", ("",)), "abc")


class TestCaps(unittest.TestCase):
    def test_caps_clause(self):
        self.assertTrue(P._is_caps(LIABLE))

    def test_normal_clause(self):
        self.assertFalse(P._is_caps(SALE))

    def test_short_shout_is_not_conspicuous(self):
        self.assertFalse(P._is_caps("NO WAY"))

    def test_caps_counted_in_evidence(self):
        self.assertEqual(ev_of(tos(LIABLE), "LIABILITY_WAIVER")["caps_count"],
                         1)
        self.assertEqual(ev_of(tos(SALE))["caps_count"], 0)


class TestReadPage(unittest.TestCase):
    def test_not_rendered_is_unreadable(self):
        e = ev_of("whatever", rendered=False)
        self.assertEqual(e["page_state"], "UNREADABLE")
        self.assertEqual(e["excerpt"], "")

    def test_short_page_is_unreadable(self):
        e = ev_of("Access denied.")
        self.assertEqual(e["page_state"], "UNREADABLE")

    def test_unknown_flag_is_unreadable(self):
        self.assertEqual(P._read_page(tos(SALE), True, "NOPE")["page_state"],
                         "UNREADABLE")

    def test_legal_markers_counted(self):
        self.assertGreaterEqual(ev_of(tos())["legal_count"], 4)
        self.assertLess(ev_of(NOT_TOS_PAGE)["legal_count"], 4)

    def test_length_bucket(self):
        self.assertEqual(ev_of(tos(pad=80))["length_bucket"], 3)
        self.assertEqual(ev_of(tos(pad=20))["length_bucket"], 1)

    def test_page_is_capped(self):
        e = ev_of(tos(pad=4000))
        self.assertEqual(e["length_bucket"], 7)


# ---------------------------------------------------------------------------
# 5. the bracket
# ---------------------------------------------------------------------------

BRACKET_CASES = [
    # (name, page, flag, case, allowed)
    ("unreadable", "Loading...", "DATA_SALE", "UNREADABLE", ["INCONCLUSIVE"]),
    ("not_tos", NOT_TOS_PAGE, "DATA_SALE", "NOT_TOS", ["INCONCLUSIVE"]),
    ("absent_long", tos(pad=80), "DATA_SALE", "ABSENT", ["CLEAN"]),
    ("absent_short", tos(pad=20), "DATA_SALE", "ABSENT", ["CLEAN"]),
    ("absent_other_flag", tos(*RED3), "AUTO_RENEWAL", "ABSENT", ["CLEAN"]),
    # --- WEAK: 0-1 distinct indicators -> INCONCLUSIVE, no model
    ("weak_one_indicator", tos("We work with third parties.",
                               "Our vendors work with third parties too."),
     "DATA_SALE", "WEAK", ["INCONCLUSIVE"]),
    ("weak_repeated_indicator", tos(*["Partner " + str(i) + " works with "
                                      "third parties." for i in range(30)]),
     "DATA_SALE", "WEAK", ["INCONCLUSIVE"]),
    ("weak_denials_only", tos(NO_SALE, NO_SALE2, NO_SALE3), "DATA_SALE",
     "WEAK", ["INCONCLUSIVE"]),
    ("weak_arb", tos("Claims are resolved by arbitration."),
     "MANDATORY_ARBITRATION", "WEAK", ["INCONCLUSIVE"]),
    # --- MODERATE: 2-4 indicators -> the side they lean, or INCONCLUSIVE
    ("moderate_red", tos(SALE), "DATA_SALE", "MODERATE",
     ["RED_FLAG", "INCONCLUSIVE"]),
    ("moderate_red_two_clauses", tos(SALE, SALE2), "DATA_SALE", "MODERATE",
     ["RED_FLAG", "INCONCLUSIVE"]),
    ("moderate_clean", tos(*DENY3), "DATA_SALE", "MODERATE",
     ["CLEAN", "INCONCLUSIVE"]),
    ("moderate_tie_leans_red", tos(SALE, NO_SALE), "DATA_SALE", "MODERATE",
     ["RED_FLAG", "INCONCLUSIVE"]),
    ("moderate_arb", tos(ARB), "MANDATORY_ARBITRATION", "MODERATE",
     ["RED_FLAG", "INCONCLUSIVE"]),
    # --- STRONG: 5+ indicators -> the full bracket
    ("strong_sale", tos(*RED3), "DATA_SALE", "STRONG",
     ["RED_FLAG", "CLEAN", "INCONCLUSIVE"]),
    ("strong_but_denied", tos(SALE4, SALE, NO_SALE, NO_SALE2, NO_SALE3),
     "DATA_SALE", "STRONG", ["CLEAN", "INCONCLUSIVE"]),
    ("license", tos(LICENSE), "CONTENT_OWNERSHIP", "STRONG",
     ["RED_FLAG", "CLEAN", "INCONCLUSIVE"]),
    ("renew", tos(RENEW, "Recurring payments are billed each billing cycle.",
                  "The plan continues until you cancel it."), "AUTO_RENEWAL",
     "STRONG", ["RED_FLAG", "CLEAN", "INCONCLUSIVE"]),
    ("arb", tos(ARB, "Claims proceed on an individual basis only.",
                "Dispute resolution is final and binding."),
     "MANDATORY_ARBITRATION", "STRONG",
     ["RED_FLAG", "CLEAN", "INCONCLUSIVE"]),
    ("change", tos(CHANGE, "We may revise the terms at our sole discretion.",
                   "Revised terms are effective upon posting."),
     "UNILATERAL_CHANGE", "STRONG", ["RED_FLAG", "CLEAN", "INCONCLUSIVE"]),
    ("terminate", tos(TERMINATE, "We may disable your account at our sole "
                      "discretion."), "ACCOUNT_TERMINATION", "STRONG",
     ["RED_FLAG", "CLEAN", "INCONCLUSIVE"]),
    ("liable", tos(LIABLE, "The service is provided as is with no "
                   "warranty.", "Our aggregate liability shall not exceed "
                   "$100.", "You agree to indemnify us."),
     "LIABILITY_WAIVER", "STRONG", ["RED_FLAG", "CLEAN", "INCONCLUSIVE"]),
    ("not_tos_with_clause", "We may sell your personal data. " * 40,
     "DATA_SALE", "NOT_TOS", ["INCONCLUSIVE"]),
]


class TestBrackets(unittest.TestCase):
    pass


def _make_bracket(i, row):
    name, page, flag, case, allowed = row

    def t(self):
        br = br_of(page, flag)
        self.assertEqual(br["case"], case, name)
        self.assertEqual(br["allowed"], allowed, name)
    t.__name__ = "test_bracket_" + name
    return t


for _i, _row in enumerate(BRACKET_CASES):
    setattr(TestBrackets, "test_bracket_" + _row[0], _make_bracket(_i, _row))


def _all_brackets():
    for row in BRACKET_CASES:
        yield row[0], br_of(row[1], row[2])
    for f in P.FLAG_KEYS:
        for extra in ((), (LIABLE,), tuple(["Partner " + str(i) + " exists."
                                            for i in range(15)])):
            yield f, br_of(tos(SALE, LICENSE, RENEW, ARB, CHANGE, TERMINATE,
                               *extra), f)


class TestBracketRules(unittest.TestCase):
    def test_every_open_range_is_two_wide(self):
        for name, br in _all_brackets():
            for o in br["allowed"]:
                for rng in (br["clarity"][o], br["scope"][o]):
                    width = rng[1] - rng[0]
                    self.assertIn(width, (0, 1), name)
                    self.assertTrue(0 <= rng[0] <= rng[1] <= 7, name)

    def test_pinned_cases_are_single_valued(self):
        for name, br in _all_brackets():
            if br["pinned"]:
                self.assertEqual(len(br["allowed"]), 1, name)
                for o in br["allowed"]:
                    self.assertEqual(br["clarity"][o], (0, 0))
                    self.assertEqual(br["scope"][o], (0, 0))

    def test_red_flag_needs_two_indicators_and_a_red_lean(self):
        for name, br in _all_brackets():
            if "RED_FLAG" in br["allowed"]:
                self.assertIn(br["case"], ("MODERATE", "STRONG"), name)
                self.assertGreaterEqual(br["strength"], 2, name)
                an = br["analysis"]
                self.assertTrue(len(an["signal"]) >= len(an["denied"]), name)

    def test_gate_tiers(self):
        """0 matches -> CLEAN; 0-1 indicators -> INCONCLUSIVE; 2-4 ->
        one-sided; 5+ -> full bracket."""
        rows = [((), "ABSENT", ["CLEAN"], True),
                (("We work with third parties.",), "WEAK",
                 ["INCONCLUSIVE"], True),
                ((SALE,), "MODERATE", ["RED_FLAG", "INCONCLUSIVE"], False),
                ((SALE, SALE2), "MODERATE", ["RED_FLAG", "INCONCLUSIVE"],
                 False),
                (RED3, "STRONG", ["RED_FLAG", "CLEAN", "INCONCLUSIVE"],
                 False)]
        for clauses, case, allowed, pinned in rows:
            br = br_of(tos(*clauses))
            self.assertEqual((br["case"], br["allowed"], br["pinned"]),
                             (case, allowed, pinned), repr(clauses))

    def test_strength_counts_distinct_families(self):
        br = br_of(tos(*RED3))
        self.assertEqual(br["strength"], len(br["analysis"]["indicators"]))
        self.assertEqual(br["analysis"]["indicators"],
                         ["sell", "share", "third party", "partner",
                          "monetize", "personalized ads", "data broker"])

    def test_repeating_one_phrase_is_one_indicator(self):
        many = ["Clause " + str(i) + ": we share data with third parties."
                for i in range(40)]
        br = br_of(tos(*many))
        self.assertEqual(br["strength"], 2)   # share + third party
        self.assertEqual(br["case"], "MODERATE")

    def test_denials_are_not_indicators(self):
        br = br_of(tos(NO_SALE, NO_SALE2, NO_SALE3))
        self.assertEqual(br["strength"], 0)
        self.assertEqual(len(br["analysis"]["denied"]), 3)

    def test_moderate_is_one_sided(self):
        for name, br in _all_brackets():
            if br["case"] == "MODERATE":
                self.assertEqual(len(br["allowed"]), 2, name)
                self.assertEqual(br["allowed"][1], "INCONCLUSIVE", name)
                self.assertNotEqual(br["allowed"][0], "INCONCLUSIVE", name)

    def test_excerpt_cap_never_hides_an_indicator(self):
        filler_clauses = ["Clause " + str(i) + " we share data with third "
                          "parties." for i in range(100)]
        page = tos(*filler_clauses, "We use personalized ads everywhere.",
                   "Zeta: we may monetize your data.")
        br = br_of(page)
        self.assertIn("personalized ads", br["analysis"]["indicators"])
        self.assertIn("monetize", br["analysis"]["indicators"])

    def test_anchor_required_for_content_ownership(self):
        br = br_of(tos("Our perpetual calendar is available worldwide.",
                       "Reproduce the error before filing a report."),
                   "CONTENT_OWNERSHIP")
        self.assertEqual(br["case"], "ABSENT")

    def test_weak_never_calls_model(self):
        fresh()
        WEB.serve(URL, tos("We work with third parties."))
        MODEL.serve("RED_FLAG", 5, 5)
        out = P._collect(facts())
        self.assertEqual(out["outcome"], "INCONCLUSIVE")
        self.assertEqual(out["case"], "WEAK")
        self.assertFalse(out["model_called"])
        self.assertEqual(MODEL.calls, 0)

    def test_weak_is_identical_on_every_run(self):
        page = tos(NO_SALE, *["Partner " + str(i) + " works with third "
                              "parties." for i in range(30)])
        outs = set()
        for _ in range(5):
            fresh()
            WEB.serve(URL, page)
            MODEL.serve("RED_FLAG", 5, 5)   # would say anything; never asked
            outs.add(P._collect(facts())["findings_key"])
        self.assertEqual(len(outs), 1)
        self.assertEqual(MODEL.calls, 0)

    def test_zero_matches_never_allow_red(self):
        for f in P.FLAG_KEYS:
            br = br_of(tos(pad=120), f)
            self.assertEqual(br["case"], "ABSENT")
            self.assertNotIn("RED_FLAG", br["allowed"])

    def test_inconclusive_always_available_when_open(self):
        for name, br in _all_brackets():
            if not br["pinned"]:
                self.assertIn("INCONCLUSIVE", br["allowed"], name)

    def test_scope_only_for_red(self):
        for name, br in _all_brackets():
            for o in br["allowed"]:
                if o != "RED_FLAG":
                    self.assertEqual(br["scope"][o], (0, 0), name)

    def test_severity_red_per_flag(self):
        for f in P.FLAGS:
            br = br_of(tos(SALE, LICENSE, RENEW, ARB, CHANGE, TERMINATE,
                           LIABLE), f[0])
            self.assertIn(br["severity_red"], (f[3], f[3] + 1))

    def test_broad_words_raise_severity(self):
        narrow = br_of(tos("We may sell your personal information to one "
                           "named partner."))
        broad = br_of(tos("We may sell your personal information at any "
                          "time to anyone."))
        self.assertEqual(narrow["severity_red"], 6)
        self.assertEqual(broad["severity_red"], 7)

    def test_caps_raise_clarity(self):
        plain = ("We are not liable for damages.", "The service is provided "
                 "as is with no warranty.")
        a = br_of(tos(*plain), "LIABILITY_WAIVER")
        b = br_of(tos("WE ARE NOT LIABLE FOR ANY DAMAGES WHATSOEVER TO "
                      "ANYONE.", plain[1]), "LIABILITY_WAIVER")
        self.assertGreater(b["clarity"]["RED_FLAG"][0],
                           a["clarity"]["RED_FLAG"][0])

    def test_range_csv_describes_every_outcome(self):
        br = br_of(tos(*RED3))
        csv = P._range_csv(br)
        for o in br["allowed"]:
            self.assertIn(o + ":c", csv)


# ---------------------------------------------------------------------------
# 6. derive, prompt, model answer
# ---------------------------------------------------------------------------


class TestDerive(unittest.TestCase):
    def setUp(self):
        self.f = facts()
        self.ev = ev_of(tos(*RED3))
        self.br = P._bracket("DATA_SALE", self.ev)

    def test_outcome_outside_bracket_becomes_inconclusive(self):
        ev = ev_of(tos(*DENY3))
        d = P._derive(self.f, ev, "RED_FLAG", 5, 5)
        self.assertEqual(d["outcome"], "INCONCLUSIVE")

    def test_pinned_clean_outcome_forced(self):
        d = P._derive(self.f, ev_of(tos(pad=100)), "RED_FLAG", 7, 7)
        self.assertEqual(d["outcome"], "CLEAN")

    def test_buckets_clamped_into_range(self):
        d = P._derive(self.f, self.ev, "RED_FLAG", 99, -4)
        lo, hi = self.br["clarity"]["RED_FLAG"]
        self.assertTrue(lo <= d["clarity_bucket"] <= hi)
        self.assertEqual(d["scope_bucket"], self.br["scope"]["RED_FLAG"][0])

    def test_severity_zero_unless_red(self):
        for o in ("CLEAN", "INCONCLUSIVE"):
            self.assertEqual(P._derive(self.f, self.ev, o, 2, 0)
                             ["severity_bucket"], 0)
        self.assertGreater(P._derive(self.f, self.ev, "RED_FLAG", 3, 2)
                           ["severity_bucket"], 0)

    def test_evidence_present(self):
        self.assertTrue(P._derive(self.f, self.ev, "RED_FLAG", 3, 2)
                        ["evidence_present"])
        self.assertFalse(P._derive(self.f, ev_of(tos(pad=100)), "CLEAN", 0, 0)
                         ["evidence_present"])

    def test_quote_for_red_is_explicit_clause(self):
        d = P._derive(self.f, ev_of(tos(SALE, SALE2, SALE3, NO_SALE)),
                      "RED_FLAG", 3, 2)
        self.assertIn(d["quote"], [P._norm(x) for x in RED3])
        self.assertTrue(len(d["quote"]) <= P.MAX_QUOTE)

    def test_quote_prefers_the_clause_over_its_heading(self):
        d = P._derive(facts(flag="MANDATORY_ARBITRATION"),
                      ev_of(tos("Class action waiver.", ARB,
                                "You agree to binding arbitration."),
                            "MANDATORY_ARBITRATION"), "RED_FLAG", 9, 9)
        self.assertEqual(d["quote"], P._norm(ARB))

    def test_reason_grammar(self):
        one = P._derive(self.f, ev_of(tos("We work with third parties.")),
                        "RED_FLAG", 0, 0)["reason"]
        two = P._derive(self.f, ev_of(tos(SALE, NO_SALE)), "RED_FLAG", 3, 2)
        self.assertIn("1 matching clause, 1 distinct indicator (third party)",
                      one)
        self.assertIn("2 matching clauses, 2 distinct indicators (sell, data "
                      "broker), 1 denial clause", two["reason"])

    def test_weak_reason_names_the_gate(self):
        r = P._derive(self.f, ev_of(tos("We work with third parties.")),
                      "RED_FLAG", 0, 0)["reason"]
        self.assertIn("too little evidence to judge (2 or more indicators "
                      "are needed)", r)

    def test_quote_for_clean_is_denial(self):
        d = P._derive(self.f, ev_of(tos(*DENY3)), "CLEAN", 2, 0)
        self.assertEqual(d["quote"], sorted(P._norm(x) for x in DENY3)[0])

    def test_no_quote_for_inconclusive(self):
        self.assertEqual(P._derive(self.f, self.ev, "INCONCLUSIVE", 1, 0)
                         ["quote"], "")

    def test_unreadable_state_scrubs_evidence(self):
        ev = dict(self.ev)
        ev["page_state"] = "UNREADABLE"
        d = P._derive(self.f, ev, "RED_FLAG", 5, 5)
        self.assertEqual(d["excerpt"], "")
        self.assertEqual(d["matched_total"], 0)
        self.assertEqual(d["outcome"], "INCONCLUSIVE")

    def test_junk_state_is_unreadable(self):
        ev = dict(self.ev)
        ev["page_state"] = "FINE"
        self.assertEqual(P._derive(self.f, ev, "RED_FLAG", 5, 5)["page_state"],
                         "UNREADABLE")

    def test_non_dict_evidence(self):
        d = P._derive(self.f, None, "RED_FLAG", 5, 5)
        self.assertEqual(d["case"], "UNREADABLE")

    def test_findings_key_joins_every_field(self):
        d = P._derive(self.f, self.ev, "RED_FLAG", 3, 2)
        key = d["findings_key"]
        self.assertTrue(key.startswith("RED_FLAG|sev"))
        self.assertIn(d["content_hash"], key)
        self.assertIn("|ev1|", key)
        self.assertIn("|len" + str(d["page_length_bucket"]) + "|", key)

    def test_reason_derived_and_bounded(self):
        for row in BRACKET_CASES:
            ev = ev_of(row[1], row[2])
            br = P._bracket(row[2], ev)
            for o in br["allowed"]:
                d = P._derive(facts(flag=row[2]), ev, o, 0, 0)
                self.assertTrue(0 < len(d["reason"]) <= P.MAX_REASON)

    def test_facts_hash_binds_concern(self):
        self.assertNotEqual(P._facts_hash(facts()),
                            P._facts_hash(facts(concern="x" * 25)))

    def test_model_called_only_when_open(self):
        self.assertTrue(P._derive(self.f, self.ev, "RED_FLAG", 3, 2)
                        ["model_called"])
        self.assertFalse(P._derive(self.f, ev_of(tos(pad=100)), "CLEAN", 0, 0)
                         ["model_called"])


class TestPrompt(unittest.TestCase):
    def setUp(self):
        self.ev = ev_of(tos(SALE, SALE2, SALE3, NO_SALE))
        self.br = P._bracket("DATA_SALE", self.ev)
        self.p = P._prompt(facts(concern="Will they sell my phone number?"),
                           self.br, self.ev)

    def test_untrusted_is_delimited(self):
        self.assertIn("<<<CLAUSES", self.p)
        self.assertIn("<<<CONCERN", self.p)

    def test_instruction_after_markers(self):
        self.assertGreater(self.p.find("Nothing between any markers"),
                           self.p.find("CLAUSES\n\n"))

    def test_lists_only_allowed_outcomes(self):
        br = P._bracket("DATA_SALE", ev_of(tos(*DENY3)))
        p = P._prompt(facts(), br, ev_of(tos(*DENY3)))
        self.assertNotIn("  - RED_FLAG", p)
        self.assertIn("  - CLEAN", p)

    def test_no_concern_block_when_empty(self):
        p = P._prompt(facts(), self.br, self.ev)
        self.assertNotIn("<<<CONCERN", p)

    def test_definition_included(self):
        self.assertIn(P._flag("DATA_SALE")[2], self.p)

    def test_asks_for_json(self):
        self.assertIn('"clarity_bucket"', self.p)


class TestModelAnswer(unittest.TestCase):
    def setUp(self):
        self.br = br_of(tos(*RED3))
        self.c = self.br["clarity"]["RED_FLAG"][0]
        self.s = self.br["scope"]["RED_FLAG"][0]

    def a(self, **k):
        return P._from_json(k, self.br)

    def test_good(self):
        self.assertEqual(self.a(outcome="RED_FLAG", clarity_bucket=self.c,
                                scope_bucket=self.s),
                         ("RED_FLAG", self.c, self.s, True))

    def test_lower_case_and_alias(self):
        self.assertTrue(self.a(outcome="red flag", clarity_bucket=self.c,
                               scope_bucket=self.s)[3])

    def test_string_numbers(self):
        self.assertTrue(self.a(outcome="RED_FLAG", clarity_bucket=str(self.c),
                               scope_bucket=str(self.s))[3])

    def test_bucket_out_of_range(self):
        self.assertFalse(self.a(outcome="RED_FLAG", clarity_bucket=7 if
                                self.c < 6 else 0, scope_bucket=self.s)[3])

    def test_bool_bucket(self):
        self.assertFalse(self.a(outcome="RED_FLAG", clarity_bucket=True,
                                scope_bucket=self.s)[3])

    def test_missing_bucket(self):
        self.assertFalse(self.a(outcome="RED_FLAG", clarity_bucket=self.c)[3])

    def test_unknown_outcome(self):
        self.assertFalse(self.a(outcome="MAYBE", clarity_bucket=1,
                                scope_bucket=0)[3])

    def test_non_dict(self):
        self.assertFalse(P._from_json("RED_FLAG", self.br)[3])

    def test_non_string_outcome(self):
        self.assertFalse(self.a(outcome=1, clarity_bucket=1, scope_bucket=0)[3])

    def test_outcome_outside_bracket(self):
        br = br_of(tos(*DENY3))
        self.assertFalse(P._from_json({"outcome": "RED_FLAG",
                                       "clarity_bucket": 3,
                                       "scope_bucket": 2}, br)[3])

    def test_inconclusive_needs_zero_scope(self):
        self.assertFalse(self.a(outcome="INCONCLUSIVE", clarity_bucket=1,
                                scope_bucket=3)[3])
        self.assertTrue(self.a(outcome="INCONCLUSIVE", clarity_bucket=1,
                               scope_bucket=0)[3])


# ---------------------------------------------------------------------------
# 7. collect, coherent, agrees, leader_failed
# ---------------------------------------------------------------------------


class TestCollect(unittest.TestCase):
    def setUp(self):
        fresh()

    def test_render_failure_is_inconclusive_without_model(self):
        WEB.down.add(URL)
        out = P._collect(facts())
        self.assertTrue(out["ok"])
        self.assertEqual(out["outcome"], "INCONCLUSIVE")
        self.assertEqual(out["case"], "UNREADABLE")
        self.assertEqual(MODEL.calls, 0)

    def test_not_tos_without_model(self):
        WEB.serve(URL, NOT_TOS_PAGE)
        out = P._collect(facts())
        self.assertEqual(out["case"], "NOT_TOS")
        self.assertEqual(MODEL.calls, 0)

    def test_absent_clean_without_model(self):
        WEB.serve(URL, tos(pad=100))
        out = P._collect(facts())
        self.assertEqual(out["outcome"], "CLEAN")
        self.assertEqual(MODEL.calls, 0)

    def test_open_case_asks_model(self):
        WEB.serve(URL, tos(*RED3))
        br = br_of(tos(*RED3))
        MODEL.serve("RED_FLAG", br["clarity"]["RED_FLAG"][0],
                    br["scope"]["RED_FLAG"][0])
        out = P._collect(facts())
        self.assertEqual(out["outcome"], "RED_FLAG")
        self.assertEqual(MODEL.calls, 1)
        self.assertIn("<<<CLAUSES", MODEL.log[0])

    def test_render_uses_text_mode(self):
        WEB.serve(URL, tos(pad=100))
        P._collect(facts())
        self.assertEqual(WEB.calls[0], (URL, "text"))

    def test_model_error_is_retry(self):
        WEB.serve(URL, tos(*RED3))
        MODEL.fail()
        out = P._collect(facts())
        self.assertFalse(out["ok"])
        self.assertTrue(out["retry"])
        self.assertIn("content_hash", out)

    def test_model_bad_answer_is_retry(self):
        WEB.serve(URL, tos(*RED3))
        MODEL.serve("PERHAPS", 1, 1)
        self.assertTrue(P._collect(facts())["retry"])


FORGERIES = [
    ("outcome", "CLEAN"),
    ("severity_bucket", 1),
    ("clarity_bucket", 0),
    ("scope_bucket", 7),
    ("evidence_present", False),
    ("page_length_bucket", 7),
    ("legal_count", 0),
    ("caps_count", 5),
    ("matched_total", 99),
    ("signal_count", 0),
    ("indicators_csv", "sell"),
    ("keyword_strength", 9),
    ("denied_count", 3),
    ("broad_count", 9),
    ("case", "MENTIONED"),
    ("allowed_csv", "RED_FLAG"),
    ("range_csv", "RED_FLAG:c7-7:s7-7"),
    ("facts_hash", "0" * 16),
    ("content_hash", "f" * 16),
    ("findings_key", "RED_FLAG|sev7"),
    ("quote", "we may do anything we like."),
    ("reason", "Trust me."),
    ("model_called", False),
    ("page_state", "BROKEN"),
    ("excerpt", "we sell everything to everyone at any time."),
    ("flag_type", "AUTO_RENEWAL"),
    ("check_id", 2),
]


class TestCoherent(unittest.TestCase):
    def setUp(self):
        fresh()
        self.f = facts()
        self.page = tos(SALE, SALE2, SALE3, NO_SALE)
        br = br_of(self.page)
        self.good = honest(self.f, self.page, "RED_FLAG",
                           br["clarity"]["RED_FLAG"][0],
                           br["scope"]["RED_FLAG"][0])

    def test_honest_is_coherent(self):
        self.assertTrue(P._coherent(self.good, self.f))

    def test_every_open_choice_is_coherent(self):
        br = br_of(self.page)
        for o in br["allowed"]:
            for c in range(br["clarity"][o][0], br["clarity"][o][1] + 1):
                for s in range(br["scope"][o][0], br["scope"][o][1] + 1):
                    self.assertTrue(P._coherent(
                        honest(self.f, self.page, o, c, s), self.f))

    def test_not_ok_refused(self):
        bad = dict(self.good)
        bad["ok"] = False
        self.assertFalse(P._coherent(bad, self.f))

    def test_non_dict_refused(self):
        self.assertFalse(P._coherent("RED_FLAG", self.f))

    def test_bool_bucket_refused(self):
        bad = dict(self.good)
        bad["clarity_bucket"] = True
        self.assertFalse(P._coherent(bad, self.f))

    def test_pinned_case_cannot_be_promoted(self):
        page = tos(pad=100)
        good = honest(self.f, page)
        bad = dict(good)
        bad["outcome"] = "RED_FLAG"
        self.assertFalse(P._coherent(bad, self.f))

    def test_evidence_swap_with_rederived_fields_changes_hash(self):
        # A leader that rebuilds EVERY field consistently from a forged
        # excerpt passes _coherent (it is arithmetic) - and is then caught by
        # _agrees, because the content hash no longer matches what the
        # validator read.
        forged_page = tos(SALE, SALE2, SALE3, "We share your personal data with everyone.")
        br = br_of(forged_page)
        forged = honest(self.f, forged_page, "RED_FLAG",
                        br["clarity"]["RED_FLAG"][0],
                        br["scope"]["RED_FLAG"][0])
        self.assertTrue(P._coherent(forged, self.f))
        self.assertFalse(P._agrees(forged, self.good))


def _make_forgery(i, row):
    key, value = row

    def t(self):
        bad = dict(self.good)
        bad[key] = value
        self.assertFalse(P._coherent(bad, self.f), key)
    t.__name__ = "test_forged_" + key
    return t


for _i, _row in enumerate(FORGERIES):
    setattr(TestCoherent, "test_forged_" + _row[0], _make_forgery(_i, _row))


AGREE_FIELDS = list(P.VECTOR_STRS) + list(P.VECTOR_INTS) + list(P.VECTOR_BOOLS)


class TestAgrees(unittest.TestCase):
    def setUp(self):
        self.f = facts()
        self.page = tos(SALE, SALE2, SALE3, NO_SALE)
        self.br = br_of(self.page)
        self.lo_c, self.hi_c = self.br["clarity"]["RED_FLAG"]
        self.lo_s, self.hi_s = self.br["scope"]["RED_FLAG"]
        self.a = honest(self.f, self.page, "RED_FLAG", self.lo_c, self.lo_s)

    def test_identical_agree(self):
        self.assertTrue(P._agrees(self.a, dict(self.a)))

    def test_tolerated_one_bucket(self):
        b = honest(self.f, self.page, "RED_FLAG", self.hi_c, self.hi_s)
        self.assertTrue(P._agrees(self.a, b))

    def test_two_buckets_apart_refused(self):
        b = dict(self.a)
        b["clarity_bucket"] = self.a["clarity_bucket"] + 2
        self.assertFalse(P._agrees(self.a, b))
        c = dict(self.a)
        c["scope_bucket"] = self.a["scope_bucket"] + 2
        self.assertFalse(P._agrees(self.a, c))

    def test_different_outcome_refused(self):
        b = honest(self.f, self.page, "INCONCLUSIVE")
        self.assertFalse(P._agrees(self.a, b))

    def test_any_honest_pair_with_same_outcome_agrees(self):
        for o in self.br["allowed"]:
            rc = self.br["clarity"][o]
            rs = self.br["scope"][o]
            for c1 in range(rc[0], rc[1] + 1):
                for c2 in range(rc[0], rc[1] + 1):
                    for s1 in range(rs[0], rs[1] + 1):
                        for s2 in range(rs[0], rs[1] + 1):
                            self.assertTrue(P._agrees(
                                honest(self.f, self.page, o, c1, s1),
                                honest(self.f, self.page, o, c2, s2)))

    def test_not_ok_refused(self):
        b = dict(self.a)
        b["ok"] = False
        self.assertFalse(P._agrees(self.a, b))
        self.assertFalse(P._agrees(None, self.a))

    def test_page_edited_between_fetches(self):
        other = honest(self.f, tos(SALE, SALE2, SALE3, NO_SALE, NO_SALE3), "RED_FLAG",
                       self.lo_c, self.lo_s)
        self.assertFalse(P._agrees(self.a, other))

    def test_shuffled_render_still_agrees(self):
        b = honest(self.f, tos(NO_SALE, SALE3, SALE2, SALE, pad=77), "RED_FLAG", self.lo_c,
                   self.lo_s)
        self.assertTrue(P._agrees(self.a, b))


def _make_agree(i, key):
    def t(self):
        b = dict(self.a)
        v = b.get(key)
        if isinstance(v, bool):
            b[key] = not v
        elif isinstance(v, int):
            b[key] = v + 1
        else:
            b[key] = str(v) + "x"
        self.assertFalse(P._agrees(self.a, b), key)
    t.__name__ = "test_field_compared_" + key
    return t


for _i, _key in enumerate(AGREE_FIELDS):
    setattr(TestAgrees, "test_field_compared_" + _key, _make_agree(_i, _key))


class TestLeaderFailed(unittest.TestCase):
    def setUp(self):
        fresh()
        self.f = facts()
        WEB.serve(URL, tos(*RED3))
        self.ch = P._content_hash(URL, "DATA_SALE", ev_of(tos(*RED3))["excerpt"])

    def payload(self, **k):
        d = {"ok": False, "retry": True, "why": "down",
             "facts_hash": P._facts_hash(self.f), "content_hash": self.ch}
        d.update(k)
        return _Return(d)

    def test_agree_when_model_down_for_me_too(self):
        MODEL.fail(1)
        self.assertTrue(P._leader_failed(self.payload(), self.f))

    def test_refuse_when_my_model_answers(self):
        br = br_of(tos(*RED3))
        MODEL.serve("RED_FLAG", br["clarity"]["RED_FLAG"][0],
                    br["scope"]["RED_FLAG"][0])
        self.assertFalse(P._leader_failed(self.payload(), self.f))

    def test_refuse_other_facts(self):
        MODEL.fail(1)
        self.assertFalse(P._leader_failed(self.payload(facts_hash="x"), self.f))

    def test_refuse_other_content(self):
        MODEL.fail(1)
        self.assertFalse(P._leader_failed(self.payload(content_hash="y"),
                                          self.f))

    def test_error_result_refused(self):
        self.assertFalse(P._leader_failed(_Rollback("x"), self.f))

    def test_non_retry_refused(self):
        self.assertFalse(P._leader_failed(_Return({"ok": True}), self.f))


# ---------------------------------------------------------------------------
# 8. the contract
# ---------------------------------------------------------------------------


class TestCheckTos(unittest.TestCase):
    def setUp(self):
        self.c = fresh()

    def test_creates_pending(self):
        out = submit(self.c)
        self.assertTrue(ok(out))
        self.assertEqual(out["check_id"], 1)
        ck = self.c.get_check(1)
        self.assertEqual(ck["status"], "PENDING")
        self.assertEqual(ck["requester"], ALICE.as_hex)
        self.assertEqual(ck["flag_type"], "DATA_SALE")
        self.assertEqual(int(self.c.total_checks), 1)

    def test_flag_normalised(self):
        out = submit(self.c, flag=" data_sale ")
        self.assertEqual(out["flag_type"], "DATA_SALE")

    def test_url_normalised(self):
        out = submit(self.c, url="HTTPS://Example-Service.com/terms#x")
        self.assertEqual(out["url"], URL)

    def test_concern_stored(self):
        submit(self.c, concern="Will they sell my phone number to anyone?")
        self.assertIn("phone number", self.c.get_check(1)["concern"])

    def _refused_moves_nothing(self, out):
        self.assertTrue(rejected(out), out)
        self.assertEqual(len(self.c.checks), 0)
        self.assertEqual(int(self.c.total_checks), 0)
        self.assertEqual(int(self.c.last_request_at.get(ALICE) or 0), 0)
        self.assertEqual(len(self.c.urls), 0)

    def test_http_refused(self):
        self._refused_moves_nothing(submit(self.c, url="http://a.com/tos"))

    def test_private_host_refused(self):
        self._refused_moves_nothing(submit(self.c, url="https://10.0.0.1/"))

    def test_unknown_flag_refused(self):
        self._refused_moves_nothing(submit(self.c, flag="SPYWARE"))

    def test_free_text_flag_refused(self):
        self._refused_moves_nothing(
            submit(self.c, flag="they sell my data"))

    def test_short_concern_refused(self):
        self._refused_moves_nothing(submit(self.c, concern="too short"))

    def test_long_concern_refused(self):
        self._refused_moves_nothing(submit(self.c, concern="x" * 201))

    def test_concern_bounds_accepted(self):
        self.assertTrue(ok(submit(self.c, concern="x" * 20)))
        self.assertTrue(ok(submit(self.c, who=BOB, flag="AUTO_RENEWAL",
                                  concern="y" * 200)))

    def test_paused_refused(self):
        send(self.c, OWNER, "set_paused", True)
        self._refused_moves_nothing(submit(self.c))

    def test_unreadable_clock_refused(self):
        MESSAGE.raw["datetime"] = ""
        self._refused_moves_nothing(submit(self.c))

    def test_rejection_counted(self):
        submit(self.c, url="http://x.com/")
        self.assertEqual(int(self.c.total_rejected), 1)

    def test_cooldown(self):
        self.assertTrue(ok(submit(self.c)))
        out = submit(self.c, flag="AUTO_RENEWAL")
        self.assertTrue(rejected(out))
        self.assertIn("120s", out["reason"])
        set_now(NOW + 119)
        self.assertTrue(rejected(submit(self.c, flag="AUTO_RENEWAL")))
        set_now(NOW + 120)
        self.assertTrue(ok(submit(self.c, flag="AUTO_RENEWAL")))

    def test_cooldown_is_per_wallet(self):
        self.assertTrue(ok(submit(self.c)))
        self.assertTrue(ok(submit(self.c, who=BOB, flag="AUTO_RENEWAL")))

    def test_refusal_does_not_start_cooldown(self):
        submit(self.c, url="http://x.com/")
        self.assertTrue(ok(submit(self.c)))

    def test_duplicate_pending_refused(self):
        submit(self.c)
        out = submit(self.c, who=BOB)
        self.assertTrue(rejected(out))
        self.assertEqual(out["pending_check_id"], 1)
        self.assertEqual(len(self.c.checks), 1)
        self.assertEqual(int(self.c.last_request_at.get(BOB) or 0), 0)

    def test_same_url_other_flag_allowed(self):
        submit(self.c)
        self.assertTrue(ok(submit(self.c, who=BOB, flag="AUTO_RENEWAL")))

    def test_recheck_after_judgment_allowed(self):
        submit(self.c)
        judge(self.c, 1, page=tos(pad=100))
        self.assertTrue(ok(submit(self.c, who=BOB)))

    def test_custom_cooldown(self):
        c = fresh(cooldown_s=0)
        self.assertTrue(ok(submit(c)))
        self.assertTrue(ok(submit(c, flag="AUTO_RENEWAL")))

    def test_constructor_clamps(self):
        c = fresh(cooldown_s=10 ** 9, stall_ttl_s=1)
        self.assertEqual(int(c.cooldown_s), P.MAX_COOLDOWN_S)
        self.assertEqual(int(c.stall_ttl_s), P.MIN_STALL_TTL_S)


class TestBatch(unittest.TestCase):
    def setUp(self):
        self.c = fresh()

    def test_batch_creates_one_per_flag(self):
        out = send(self.c, ALICE, "batch_check", URL,
                   ["DATA_SALE", "AUTO_RENEWAL", "LIABILITY_WAIVER"])
        self.assertTrue(ok(out))
        self.assertEqual(out["check_ids"], [1, 2, 3])
        self.assertEqual(out["batch_id"], 1)
        for cid in (1, 2, 3):
            self.assertEqual(self.c.get_check(cid)["batch_id"], 1)

    def test_batch_accepts_csv(self):
        out = send(self.c, ALICE, "batch_check", URL, "data_sale, auto_renewal")
        self.assertEqual(out["flag_types"], ["DATA_SALE", "AUTO_RENEWAL"])

    def test_all_seven(self):
        out = send(self.c, ALICE, "batch_check", URL, list(P.FLAG_KEYS))
        self.assertEqual(len(out["check_ids"]), 7)

    def _refused(self, arg):
        out = send(self.c, ALICE, "batch_check", URL, arg)
        self.assertTrue(rejected(out), out)
        self.assertEqual(len(self.c.checks), 0)
        self.assertEqual(int(self.c.total_batches), 0)
        self.assertEqual(int(self.c.last_request_at.get(ALICE) or 0), 0)

    def test_unknown_flag_refuses_whole_batch(self):
        self._refused(["DATA_SALE", "NOPE"])

    def test_duplicate_flag_refused(self):
        self._refused(["DATA_SALE", "data_sale"])

    def test_empty_refused(self):
        self._refused([])

    def test_non_list_refused(self):
        self._refused(42)

    def test_too_many_refused(self):
        self._refused(list(P.FLAG_KEYS) + ["DATA_SALE"])

    def test_pending_flag_refuses_whole_batch(self):
        submit(self.c, who=BOB)
        out = send(self.c, ALICE, "batch_check", URL,
                   ["AUTO_RENEWAL", "DATA_SALE"])
        self.assertTrue(rejected(out))
        self.assertEqual(len(self.c.checks), 1)

    def test_batch_shares_cooldown(self):
        send(self.c, ALICE, "batch_check", URL, ["AUTO_RENEWAL"])
        self.assertTrue(rejected(submit(self.c, url=URL2)))

    def test_batch_bad_url(self):
        self._refused_url = send(self.c, ALICE, "batch_check", "http://a.com",
                                 ["DATA_SALE"])
        self.assertTrue(rejected(self._refused_url))

    def test_batch_paused(self):
        send(self.c, OWNER, "set_paused", True)
        self._refused(["DATA_SALE"])


class TestJudge(unittest.TestCase):
    def setUp(self):
        self.c = fresh()
        submit(self.c)

    def red(self, page):
        br = br_of(page)
        return ("RED_FLAG", br["clarity"]["RED_FLAG"][0],
                br["scope"]["RED_FLAG"][0])

    def test_red_flag_judgment(self):
        page = tos(SALE, SALE2, SALE3, NO_SALE)
        out = judge(self.c, 1, page=page, answer=self.red(page))
        self.assertTrue(out["judged"], out)
        self.assertEqual(out["outcome"], "RED_FLAG")
        ck = self.c.get_check(1)
        self.assertEqual(ck["status"], "JUDGED")
        self.assertEqual(ck["severity_bucket"], 6)
        self.assertTrue(ck["evidence_present"])
        self.assertIn(ck["quote"], [P._norm(x) for x in RED3])
        self.assertEqual(ck["content_hash"], P._content_hash(
            URL, "DATA_SALE", ev_of(page)["excerpt"]))
        self.assertEqual(int(self.c.total_judgments), 1)

    def test_permissionless_and_while_paused(self):
        send(self.c, OWNER, "set_paused", True)
        out = judge(self.c, 1, page=tos(pad=100), who=CAROL)
        self.assertTrue(out["judged"])

    def test_unreadable_is_inconclusive(self):
        WEB.down.add(URL)
        out = judge(self.c, 1)
        self.assertEqual(out["outcome"], "INCONCLUSIVE")
        self.assertEqual(self.c.get_check(1)["case"], "UNREADABLE")
        self.assertEqual(MODEL.calls, 0)

    def test_login_wall_is_inconclusive(self):
        out = judge(self.c, 1, page="Log in to continue\nEmail\nPassword\n"
                    "Forgot password?\n" + filler(10))
        self.assertEqual(out["outcome"], "INCONCLUSIVE")

    def test_clean_by_denial(self):
        page = tos(*DENY3)
        br = br_of(page)
        out = judge(self.c, 1, page=page,
                    answer=("CLEAN", br["clarity"]["CLEAN"][0], 0))
        self.assertEqual(out["outcome"], "CLEAN")
        self.assertEqual(self.c.get_check(1)["severity_bucket"], 0)

    def test_model_disagreement_settles_nothing(self):
        page = tos(*RED3)
        WEB.serve(URL, page)
        br = br_of(page)
        MODEL.script(("RED_FLAG", br["clarity"]["RED_FLAG"][0],
                      br["scope"]["RED_FLAG"][0]),
                     ("CLEAN", br["clarity"]["CLEAN"][0], 0))
        out = send(self.c, STRANGER, "judge_check", 1)
        self.assertTrue(ok(out))
        self.assertFalse(out["judged"])
        ck = self.c.get_check(1)
        self.assertEqual(ck["status"], "PENDING")
        self.assertEqual(ck["judge_attempts"], 1)
        self.assertEqual(ck["outcome"], "")
        self.assertEqual(int(self.c.total_unsettled), 1)

    def test_page_changed_between_fetches_settles_nothing(self):
        WEB.script(URL, tos(pad=100), tos(*RED3))
        MODEL.serve(*self.red(tos(*RED3)))
        out = send(self.c, STRANGER, "judge_check", 1)
        self.assertFalse(out["judged"])

    def test_forged_leader_refused(self):
        page = tos(*DENY3)
        WEB.serve(URL, page)
        br = br_of(page)
        MODEL.serve("CLEAN", br["clarity"]["CLEAN"][0], 0)
        forged = honest(facts(), page, "CLEAN")
        forged = dict(forged)
        forged["outcome"] = "RED_FLAG"
        FORGE["payload"] = forged
        out = send(self.c, STRANGER, "judge_check", 1)
        self.assertFalse(out["judged"])

    def test_leader_dies(self):
        FORGE["leader_dies"] = True
        out = send(self.c, STRANGER, "judge_check", 1)
        self.assertFalse(out["judged"])
        self.assertEqual(self.c.get_check(1)["status"], "PENDING")

    def test_both_models_down_settles_nothing(self):
        WEB.serve(URL, tos(*RED3))
        MODEL.fail(2)
        out = send(self.c, STRANGER, "judge_check", 1)
        self.assertFalse(out["judged"])

    def test_retry_after_unsettled(self):
        FORGE["leader_dies"] = True
        send(self.c, STRANGER, "judge_check", 1)
        FORGE["leader_dies"] = False
        out = judge(self.c, 1, page=tos(pad=100))
        self.assertTrue(out["judged"])
        self.assertEqual(self.c.get_check(1)["judge_attempts"], 2)

    def test_judged_is_frozen(self):
        judge(self.c, 1, page=tos(pad=100))
        before = self.c.get_check(1)
        out = judge(self.c, 1, page=tos(*RED3), answer=self.red(tos(*RED3)))
        self.assertTrue(rejected(out))
        self.assertEqual(self.c.get_check(1), before)

    def test_unknown_check(self):
        self.assertTrue(rejected(send(self.c, STRANGER, "judge_check", 99)))
        self.assertTrue(rejected(send(self.c, STRANGER, "judge_check", "x")))

    def test_clock_unreadable(self):
        MESSAGE.raw["datetime"] = "bad"
        self.assertTrue(rejected(send(self.c, STRANGER, "judge_check", 1)))

    def test_judgment_frees_pending_slot(self):
        judge(self.c, 1, page=tos(pad=100))
        self.assertEqual(int(self.c.pending.get("DATA_SALE|" + URL) or 0), 0)

    def test_stored_record_is_rederived(self):
        page = tos(*RED3)
        WEB.serve(URL, page)
        MODEL.serve(*self.red(page))
        send(self.c, STRANGER, "judge_check", 1)
        v = self.c.verify_check(1)
        self.assertTrue(v["verified"], v)

    def test_concern_reaches_prompt(self):
        c = fresh()
        submit(c, concern="Do they sell my location history to brokers?")
        page = tos(*RED3)
        judge(c, 1, page=page, answer=self.red(page))
        self.assertIn("location history", MODEL.log[0])

    def test_findings_key_stored(self):
        page = tos(*RED3)
        out = judge(self.c, 1, page=page, answer=self.red(page))
        self.assertTrue(out["findings_key"].startswith("RED_FLAG|"))


class TestStalled(unittest.TestCase):
    def setUp(self):
        self.c = fresh()
        submit(self.c)

    def test_too_early(self):
        set_now(NOW + 3599)
        out = send(self.c, STRANGER, "settle_stalled", 1)
        self.assertTrue(rejected(out))
        self.assertEqual(out["stalls_at"], NOW + 3600)

    def test_settles_permissionless_while_paused(self):
        send(self.c, OWNER, "set_paused", True)
        set_now(NOW + 3600)
        out = send(self.c, CAROL, "settle_stalled", 1)
        self.assertTrue(ok(out))
        ck = self.c.get_check(1)
        self.assertEqual(ck["status"], "STALLED")
        self.assertEqual(ck["outcome"], "")
        self.assertEqual(int(self.c.total_stalled), 1)

    def test_stalled_is_frozen(self):
        set_now(NOW + 3600)
        send(self.c, STRANGER, "settle_stalled", 1)
        self.assertTrue(rejected(send(self.c, STRANGER, "settle_stalled", 1)))
        self.assertTrue(rejected(judge(self.c, 1, page=tos(pad=100))))

    def test_stalled_frees_slot(self):
        set_now(NOW + 3600)
        send(self.c, STRANGER, "settle_stalled", 1)
        self.assertTrue(ok(submit(self.c, who=BOB)))

    def test_judged_cannot_stall(self):
        judge(self.c, 1, page=tos(pad=100))
        set_now(NOW + 10 ** 6)
        self.assertTrue(rejected(send(self.c, STRANGER, "settle_stalled", 1)))

    def test_stalled_not_in_stats(self):
        set_now(NOW + 3600)
        send(self.c, STRANGER, "settle_stalled", 1)
        self.assertEqual(self.c.get_flag_stats("DATA_SALE")["judged_checks"], 0)

    def test_ttl_snapshotted(self):
        c = fresh(stall_ttl_s=600)
        submit(c)
        set_now(NOW + 600)
        self.assertTrue(ok(send(c, STRANGER, "settle_stalled", 1)))

    def test_unknown(self):
        self.assertTrue(rejected(send(self.c, STRANGER, "settle_stalled", 7)))


class TestStats(unittest.TestCase):
    def setUp(self):
        self.c = fresh(cooldown_s=0)

    def red_judge(self, cid, page, url=URL):
        br = br_of(page)
        return judge(self.c, cid, page=page, url=url,
                     answer=("RED_FLAG", br["clarity"]["RED_FLAG"][0],
                             br["scope"]["RED_FLAG"][0]))

    def test_counts_and_flagged_urls(self):
        submit(self.c)
        self.red_judge(1, tos(*RED3))
        submit(self.c, url=URL2)
        judge(self.c, 2, page=tos(pad=100), url=URL2)
        s = self.c.get_flag_stats("DATA_SALE")
        self.assertEqual(s["judged_checks"], 2)
        self.assertEqual(s["by_outcome"]["RED_FLAG"], 1)
        self.assertEqual(s["by_outcome"]["CLEAN"], 1)
        self.assertEqual(s["urls_flagged"], 1)
        self.assertEqual(s["urls_judged"], 2)

    def test_later_clean_unflags(self):
        submit(self.c)
        self.red_judge(1, tos(*RED3))
        submit(self.c)
        judge(self.c, 2, page=tos(pad=100))
        s = self.c.get_flag_stats("DATA_SALE")
        self.assertEqual(s["urls_flagged"], 0)
        self.assertEqual(s["urls_judged"], 1)
        self.assertEqual(s["judged_checks"], 2)

    def test_repeat_red_counts_url_once(self):
        for cid in (1, 2):
            submit(self.c)
            self.red_judge(cid, tos(*RED3))
        self.assertEqual(self.c.get_flag_stats("DATA_SALE")["urls_flagged"], 1)

    def test_unknown_flag(self):
        self.assertFalse(self.c.get_flag_stats("NOPE")["found"])

    def test_url_report(self):
        submit(self.c)
        send(self.c, ALICE, "batch_check", URL, ["AUTO_RENEWAL",
                                                 "LIABILITY_WAIVER"])
        self.red_judge(1, tos(*RED3))
        r = self.c.get_url_report("https://EXAMPLE-service.com/terms#top")
        self.assertTrue(r["found"])
        self.assertEqual(r["total_checks"], 3)
        self.assertEqual([x["check_id"] for x in r["checks"]], [3, 2, 1])
        self.assertEqual(r["latest"], {"DATA_SALE": "RED_FLAG"})
        self.assertEqual(r["red_flags"], ["DATA_SALE"])

    def test_url_report_unknown_and_bad(self):
        self.assertFalse(self.c.get_url_report(URL2)["found"])
        self.assertFalse(self.c.get_url_report("http://x.com")["found"])

    def test_recent(self):
        for f in ("DATA_SALE", "AUTO_RENEWAL", "LIABILITY_WAIVER"):
            submit(self.c, flag=f)
        r = self.c.get_recent_checks(2)
        self.assertEqual(r["total"], 3)
        self.assertEqual([x["check_id"] for x in r["items"]], [3, 2])
        self.assertEqual(len(self.c.get_recent_checks(999)["items"]), 3)
        self.assertEqual(self.c.get_recent_checks(-1)["items"], [])

    def test_by_requester(self):
        submit(self.c)
        submit(self.c, who=BOB, flag="AUTO_RENEWAL")
        self.assertEqual(self.c.get_checks_by_requester(BOB.as_hex)["ids"], [2])
        self.assertEqual(self.c.get_checks_by_requester("junk")["ids"], [])

    def test_get_check_missing(self):
        self.assertFalse(self.c.get_check(5)["found"])

    def test_stats_status_counts(self):
        submit(self.c)
        submit(self.c, flag="AUTO_RENEWAL")
        judge(self.c, 1, page=tos(pad=100))
        s = self.c.get_stats()
        self.assertEqual(s["status_counts"], {"PENDING": 1, "JUDGED": 1,
                                              "STALLED": 0})
        self.assertEqual(s["urls"], 1)

    def test_vocabulary(self):
        v = self.c.get_vocabulary()
        self.assertEqual([f["key"] for f in v["flags"]], list(P.FLAG_KEYS))
        for f in v["flags"]:
            self.assertTrue(f["description"])

    def test_config(self):
        cfg = self.c.get_config()
        self.assertEqual(cfg["payable_methods"], 0)
        self.assertFalse(cfg["custody"])
        self.assertIn("content_hash", cfg["compared_exactly"])
        self.assertEqual(cfg["compared_within_one"],
                         ["clarity_bucket", "scope_bucket"])

    def test_preview_bracket(self):
        p = self.c.preview_bracket("DATA_SALE", tos(*RED3))
        self.assertEqual(p["case"], "STRONG")
        self.assertEqual(p["keyword_strength"], 7)
        self.assertTrue(p["model_called"])
        self.assertIn("RED_FLAG", p["allowed"])
        self.assertFalse(self.c.preview_bracket("X", "y")["ok"])


class TestVerify(unittest.TestCase):
    def setUp(self):
        self.c = fresh()
        submit(self.c)
        page = tos(SALE, SALE2, SALE3, LIABLE)
        br = br_of(page)
        judge(self.c, 1, page=page,
              answer=("RED_FLAG", br["clarity"]["RED_FLAG"][1],
                      br["scope"]["RED_FLAG"][1]))

    def test_verified(self):
        v = self.c.verify_check(1)
        self.assertTrue(v["verified"])
        self.assertGreaterEqual(len(v["checks"]), 15)

    def test_tamper_detected(self):
        for field, value in (("severity_bucket", 1), ("content_hash", "0"),
                             ("quote", "nothing"), ("case", "ABSENT"),
                             ("excerpt", "we sell nothing.")):
            c = fresh()
            submit(c)
            page = tos(*RED3)
            br = br_of(page)
            judge(c, 1, page=page, answer=("RED_FLAG",
                                           br["clarity"]["RED_FLAG"][0],
                                           br["scope"]["RED_FLAG"][0]))
            setattr(c.checks[0], field, value)
            self.assertFalse(c.verify_check(1)["verified"], field)

    def test_pending_not_verified(self):
        submit(self.c, who=BOB, flag="AUTO_RENEWAL")
        self.assertFalse(self.c.verify_check(2)["judged"])

    def test_missing(self):
        self.assertFalse(self.c.verify_check(9)["found"])


class TestValueLedger(unittest.TestCase):
    """No method is payable and nothing costs anything. If value ever arrives,
    it is the sender's, on every path, refused or not."""

    def setUp(self):
        self.c = fresh()

    def test_value_on_refusal_is_refundable(self):
        out = send(self.c, ALICE, "check_tos", "http://x.com/", "DATA_SALE", "",
                   value=5)
        self.assertTrue(rejected(out))
        self.assertEqual(out["refunded_wei"], "5")
        self.assertEqual(self.c.get_refund(ALICE.as_hex)["refund_wei"], "5")

    def test_value_on_success_is_refundable(self):
        send(self.c, ALICE, "check_tos", URL, "DATA_SALE", "", value=7)
        self.assertEqual(self.c.get_refund(ALICE.as_hex)["refund_wei"], "7")

    def test_claim_refund_pays_and_balances(self):
        send(self.c, ALICE, "check_tos", "http://x.com/", "DATA_SALE", "",
             value=9)
        out = send(self.c, ALICE, "claim_refund")
        self.assertTrue(ok(out))
        self.assertEqual(TRANSFERS, [(ALICE.as_hex, 9)])
        s = self.c.get_stats()
        self.assertEqual(s["balance_wei"], "0")
        self.assertTrue(s["ledger_balanced"])

    def test_nothing_to_claim(self):
        self.assertTrue(rejected(send(self.c, ALICE, "claim_refund")))
        self.assertEqual(TRANSFERS, [])

    def test_claim_refund_while_paused(self):
        send(self.c, ALICE, "judge_check", 1, value=3)
        send(self.c, OWNER, "set_paused", True)
        self.assertTrue(ok(send(self.c, ALICE, "claim_refund")))

    def test_every_write_banks(self):
        for method, args in (("check_tos", (URL, "DATA_SALE", "")),
                             ("batch_check", (URL2, ["AUTO_RENEWAL"])),
                             ("judge_check", (99,)),
                             ("settle_stalled", (99,)),
                             ("set_paused", (False,)),
                             ("transfer_ownership", ("junk",))):
            c = fresh()
            send(c, BOB, method, *args, value=11)
            self.assertEqual(c.get_refund(BOB.as_hex)["refund_wei"], "11",
                             method)
            self.assertTrue(c.get_stats()["ledger_balanced"], method)

    def test_no_double_credit(self):
        send(self.c, ALICE, "check_tos", "http://x.com/", "DATA_SALE", "",
             value=4)
        send(self.c, ALICE, "claim_refund")
        self.assertTrue(rejected(send(self.c, ALICE, "claim_refund")))
        self.assertEqual(TRANSFERS, [(ALICE.as_hex, 4)])


class TestOwner(unittest.TestCase):
    def setUp(self):
        self.c = fresh()

    def test_only_owner_pauses(self):
        self.assertTrue(rejected(send(self.c, STRANGER, "set_paused", True)))
        self.assertFalse(self.c.paused)
        self.assertTrue(ok(send(self.c, OWNER, "set_paused", True)))
        self.assertTrue(self.c.paused)
        self.assertTrue(ok(send(self.c, OWNER, "set_paused", 0)))
        self.assertFalse(self.c.paused)

    def test_transfer_ownership(self):
        self.assertTrue(rejected(send(self.c, STRANGER, "transfer_ownership",
                                      STRANGER.as_hex)))
        self.assertTrue(rejected(send(self.c, OWNER, "transfer_ownership",
                                      "0x" + "0" * 40)))
        self.assertTrue(ok(send(self.c, OWNER, "transfer_ownership",
                                BOB.as_hex)))
        self.assertTrue(rejected(send(self.c, OWNER, "set_paused", True)))
        self.assertTrue(ok(send(self.c, BOB, "set_paused", True)))

    def test_owner_has_no_other_power(self):
        names = [n.name for n in ast.walk(TREE)
                 if isinstance(n, ast.FunctionDef)]
        for bad in ("withdraw", "sweep", "rescue", "set_flags", "set_cooldown",
                    "delete_check", "edit_check", "set_outcome"):
            self.assertNotIn(bad, names)


# ---------------------------------------------------------------------------
# 9. real renders (test/fixtures, captured on Studio Dev by probe.mjs)
# ---------------------------------------------------------------------------

REAL = [
    # (fixture, flag, case, strength) on the renders captured on Studio Dev
    # by the v1.2.0 probe (docs/probe-report.md). The nine seed checks first.
    ("x_tos.txt", "CONTENT_OWNERSHIP", "STRONG", 6),
    ("x_tos.txt", "MANDATORY_ARBITRATION", "STRONG", 5),
    ("duckduckgo_terms.txt", "DATA_SALE", "ABSENT", 0),
    ("duckduckgo_terms.txt", "MANDATORY_ARBITRATION", "ABSENT", 0),
    ("discord_terms.txt", "CONTENT_OWNERSHIP", "STRONG", 7),
    ("discord_terms.txt", "ACCOUNT_TERMINATION", "MODERATE", 4),
    ("zoom_terms.txt", "UNILATERAL_CHANGE", "MODERATE", 4),
    ("github_terms.txt", "CONTENT_OWNERSHIP", "MODERATE", 4),
    ("example_com.txt", "DATA_SALE", "UNREADABLE", 0),
    # ...and the ones that were considered and left out.
    ("zoom_terms.txt", "DATA_SALE", "ABSENT", 0),
    ("x_tos.txt", "DATA_SALE", "WEAK", 0),
    ("wikipedia_terms.txt", "ACCOUNT_TERMINATION", "ABSENT", 0),
]


class TestRealRenders(unittest.TestCase):
    def _real(self, name):
        path = FIXTURES / name
        if not path.exists():
            self.skipTest("no fixture " + name)
        return path.read_text(encoding="utf8")

    def test_fixtures_bracket_as_captured(self):
        for name, flag, case, strength in REAL:
            br = br_of(self._real(name), flag)
            self.assertEqual((br["case"], br["strength"]), (case, strength),
                             name + " " + flag)

    def test_seed_is_at_least_five_decisive_or_model_judged(self):
        decisive = 0
        for name, flag, _case, _st in REAL[:9]:
            br = br_of(self._real(name), flag)
            if br["allowed"] == ["CLEAN"] or not br["pinned"]:
                decisive += 1
        self.assertGreaterEqual(decisive, 5)

    def test_zoom_integrations_are_not_data_sharing(self):
        # "in connection with third party offerings" and "you may not share
        # an account" were false indicator / false denial in the first
        # v1.2.0 draft.
        an = br_of(self._real("zoom_terms.txt"))["analysis"]
        self.assertEqual(an["signal"], [])
        self.assertEqual(an["denied"], [])

    def test_feedback_licences_are_not_content_licences(self):
        for name in ("discord_terms.txt", "github_terms.txt"):
            an = br_of(self._real(name), "CONTENT_OWNERSHIP")["analysis"]
            for s in an["signal"]:
                self.assertNotIn("feedback", s, name)

    def test_quotes_are_about_the_flag(self):
        want = {("discord_terms.txt", "CONTENT_OWNERSHIP"): "sublicensable",
                ("github_terms.txt", "CONTENT_OWNERSHIP"): "your content",
                ("zoom_terms.txt", "UNILATERAL_CHANGE"): "revised terms",
                ("x_tos.txt", "CONTENT_OWNERSHIP"): "you grant us"}
        for (name, flag), needle in want.items():
            d = P._derive(facts(flag=flag), ev_of(self._real(name), flag),
                          "RED_FLAG", 9, 9)
            self.assertIn(needle, d["quote"], name)

    def test_x_disclosure_clause_is_a_denial(self):
        an = br_of(self._real("x_tos.txt"))["analysis"]
        self.assertEqual(an["signal"], [])
        self.assertTrue(any("do not disclose" in s for s in an["denied"]))

    def test_discord_termination_leans_red(self):
        br = br_of(self._real("discord_terms.txt"), "ACCOUNT_TERMINATION")
        self.assertEqual(br["allowed"], ["RED_FLAG", "INCONCLUSIVE"])
        d = P._derive(facts(url="https://discord.com/terms",
                            flag="ACCOUNT_TERMINATION"),
                      ev_of(self._real("discord_terms.txt"),
                            "ACCOUNT_TERMINATION"), "RED_FLAG", 9, 9)
        self.assertIn("for any reason", d["quote"])

    def test_x_arbitration_quote_is_a_clause(self):
        page = self._real("x_tos.txt")
        d = P._derive(facts(url="https://x.com/en/tos",
                            flag="MANDATORY_ARBITRATION"),
                      ev_of(page, "MANDATORY_ARBITRATION"), "RED_FLAG", 9, 9)
        self.assertGreater(len(d["quote"]), 80)

    def test_x_license_is_quoted(self):
        page = self._real("x_tos.txt")
        d = P._derive(facts(url="https://x.com/en/tos",
                            flag="CONTENT_OWNERSHIP"),
                      ev_of(page, "CONTENT_OWNERSHIP"), "RED_FLAG", 9, 9)
        self.assertIn("royalty-free license", d["quote"])

    def test_example_com_is_unreadable_not_guessed(self):
        f = facts(url="https://example.com/")
        d = P._derive(f, ev_of(self._real("example_com.txt")), "RED_FLAG", 3, 3)
        self.assertEqual(d["outcome"], "INCONCLUSIVE")
        self.assertFalse(d["model_called"])

    def test_real_page_length_buckets(self):
        self.assertEqual(ev_of(self._real("duckduckgo_terms.txt"))
                         ["length_bucket"], 3)
        self.assertEqual(ev_of(self._real("wikipedia_terms.txt"))
                         ["length_bucket"], 4)
        self.assertEqual(ev_of(self._real("x_tos.txt"))["length_bucket"], 7)
        self.assertEqual(ev_of(self._real("discord_terms.txt"))
                         ["length_bucket"], 6)

    def test_real_renders_are_deterministic(self):
        for path in sorted(FIXTURES.glob("*.txt")):
            page = path.read_text(encoding="utf8")
            for f in P.FLAG_KEYS:
                self.assertEqual(ev_of(page, f), ev_of(page, f), path.name)

    def test_real_render_brackets_have_two_wide_ranges(self):
        for path in sorted(FIXTURES.glob("*.txt")):
            page = path.read_text(encoding="utf8")
            for f in P.FLAG_KEYS:
                br = br_of(page, f)
                for o in br["allowed"]:
                    self.assertLessEqual(br["clarity"][o][1]
                                         - br["clarity"][o][0], 1)

    def test_repeat_renders_hash_identically(self):
        groups = {}
        for path in sorted(FIXTURES.glob("*_render*.txt")):
            stem = path.name.split("_render")[0]
            groups.setdefault(stem, []).append(path.read_text(encoding="utf8"))
        for stem, pages in groups.items():
            for f in P.FLAG_KEYS:
                hashes = set()
                for page in pages:
                    hashes.add(P._content_hash(URL, f, ev_of(page, f)
                                               ["excerpt"]))
                self.assertEqual(len(hashes), 1, stem + " " + f)


# ---------------------------------------------------------------------------
# 10. the source itself
# ---------------------------------------------------------------------------


def _class_methods(name):
    cls = [n for n in TREE.body if isinstance(n, ast.ClassDef)
           and n.name == name][0]
    return {f.name: f for f in cls.body if isinstance(f, ast.FunctionDef)}


def _decos(fn):
    return [ast.unparse(d) for d in fn.decorator_list]


METHODS = _class_methods("TOSGuard")
WRITES = {k: f for k, f in METHODS.items()
          if any(d.startswith("gl.public.write") for d in _decos(f))}
VIEWS = {k: f for k, f in METHODS.items()
         if any(d == "gl.public.view" for d in _decos(f))}


class TestSource(unittest.TestCase):
    def test_zero_raise(self):
        self.assertEqual([n.lineno for n in ast.walk(TREE)
                          if isinstance(n, ast.Raise)], [])

    def test_no_str_replace(self):
        self.assertEqual([n.lineno for n in ast.walk(TREE)
                          if isinstance(n, ast.Call)
                          and isinstance(n.func, ast.Attribute)
                          and n.func.attr == "replace"], [])

    def test_header(self):
        lines = SRC_TEXT.split("\n")
        self.assertEqual(lines[0], "# v0.3.0")
        self.assertTrue(lines[1].startswith('# { "Depends": "py-genlayer:'))
        self.assertEqual(lines[2], "import genlayer as gl")

    def test_runner_pinned(self):
        self.assertNotIn("py-genlayer:test", SRC_TEXT)
        self.assertNotIn("py-genlayer:latest", SRC_TEXT)

    def test_no_undefined_names(self):
        self.assertEqual(undefined_names(SOURCE), [])

    def test_no_payable_methods(self):
        for k, f in WRITES.items():
            for d in _decos(f):
                self.assertFalse(d.endswith("payable"), k)

    def test_every_write_banks_first(self):
        for k, f in WRITES.items():
            body = f.body
            if isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant):
                body = body[1:]
            self.assertIn("self._bank()", ast.unparse(body[0]), k)

    def test_nondet_closures_capture_no_self(self):
        for name, f in METHODS.items():
            for inner in ast.walk(f):
                if isinstance(inner, ast.FunctionDef) and inner is not f:
                    ids = {n.id for n in ast.walk(inner)
                           if isinstance(n, ast.Name)}
                    if name != "verify_check":
                        self.assertNotIn("self", ids, name + "." + inner.name)

    def test_transfers_only_in_pay(self):
        callers = {f.name for f in ast.walk(TREE)
                   if isinstance(f, ast.FunctionDef)
                   for s in ast.walk(f) if isinstance(s, ast.Call)
                   and isinstance(s.func, ast.Attribute)
                   and s.func.attr == "emit_transfer"}
        self.assertEqual(callers, {"_pay"})

    def test_only_gate_reads_paused(self):
        readers = set()
        for k, f in METHODS.items():
            for s in ast.walk(f):
                if isinstance(s, ast.Attribute) and s.attr == "paused" \
                        and isinstance(s.ctx, ast.Load) \
                        and k not in ("get_stats", "get_config"):
                    readers.add(k)
        self.assertEqual(readers, {"_gate"})

    def test_required_methods_exist(self):
        for m in ("check_tos", "batch_check", "judge_check", "settle_stalled"):
            self.assertIn(m, WRITES)
        for m in ("get_check", "get_url_report", "get_flag_stats",
                  "get_recent_checks", "get_vocabulary", "get_config",
                  "verify_check"):
            self.assertIn(m, VIEWS)

    def test_no_counter_before_refusal(self):
        bad = []
        for name, f in WRITES.items():
            ev = []
            for sub in ast.walk(f):
                if isinstance(sub, ast.Assign):
                    for t in sub.targets:
                        tx = ast.unparse(t)
                        if tx.startswith("self.total_") or \
                                tx.startswith("self.last_request_at") or \
                                tx.startswith("self.pending"):
                            ev.append((sub.lineno, "c"))
                if isinstance(sub, ast.Call) and \
                        ast.unparse(sub.func) == "self._new_check":
                    ev.append((sub.lineno, "c"))
                if isinstance(sub, ast.Return) and sub.value is not None \
                        and "_refuse" in ast.unparse(sub.value):
                    ev.append((sub.lineno, "r"))
            ev.sort()
            seen = False
            for _, k in ev:
                if k == "c":
                    seen = True
                elif seen:
                    bad.append(name)
                    break
        self.assertEqual(bad, [])

    def test_compared_vector_covers_brief_fields(self):
        vec = set(P.VECTOR_STRS) | set(P.VECTOR_INTS) | set(P.VECTOR_BOOLS) \
            | set(P.VECTOR_TOLERATED)
        for f in ("outcome", "severity_bucket", "clarity_bucket",
                  "scope_bucket", "evidence_present", "content_hash",
                  "page_length_bucket"):
            self.assertIn(f, vec)

    def test_write_judgment_reads_only_derived(self):
        src = ast.unparse(METHODS["_write_judgment"])
        self.assertNotIn("out.get", src)
        for f in ("outcome", "severity_bucket", "clarity_bucket",
                  "scope_bucket", "evidence_present", "content_hash",
                  "page_length_bucket", "excerpt", "quote", "findings_key"):
            self.assertIn("d['" + f + "']", src)


if __name__ == "__main__":
    unittest.main(verbosity=1)
