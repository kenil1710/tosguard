# v0.3.0
# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng" }
import genlayer as gl
from genlayer import *

import json

# Throwaway diagnostic, NOT part of TOSGuard. It answers the question the whole
# project stands on: what text does a validator ACTUALLY see when it renders a
# Terms of Service page? The clause scanner in TOSGuard is written against
# these bytes, not against what a browser shows a human.


class RenderProbe(gl.contract.Contract):
	pages: gl.storage.TreeMap[str, str]
	errors: gl.storage.TreeMap[str, str]

	def __init__(self):
		pass

	@gl.public.write
	def probe(self, url: str, wait: str) -> None:
		target = str(url)
		hold = str(wait) if wait else "2s"

		def leader_fn() -> dict:
			try:
				txt = gl.nondet.web.render(target, mode="text", wait_after_loaded=hold)
				return {"ok": True, "text": str(txt)[:200000]}
			except Exception as e:
				return {"ok": False, "text": "", "err": str(e)[:600]}

		def validator_fn(leader_result) -> bool:
			return isinstance(leader_result, gl.vm.Return)

		res = gl.vm.run_nondet(leader_fn, validator_fn)
		self.pages[target] = str(res.get("text", ""))
		self.errors[target] = str(res.get("err", ""))

	@gl.public.view
	def window(self, url: str, start: int, count: int) -> str:
		t = self.pages.get(str(url)) or ""
		return json.dumps({"len": len(t), "err": self.errors.get(str(url)) or "",
			"text": t[int(start):int(start) + int(count)]})
