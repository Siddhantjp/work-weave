"""Task runner, LLM cache round-trip and extraction edge cases. Offline."""
import time

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration

from app import tasks
from app.llm import SQLiteLLMCache
from app.search.extraction import Evidence, Extraction, verify_extraction


def wait(tid, owner, secs=5):
    end = time.time() + secs
    while time.time() < end:
        t = tasks.get(tid, owner)
        if t["status"] != "running":
            return t
        time.sleep(0.02)
    raise AssertionError("task did not finish")


def test_task_collects_events_and_result():
    tid = tasks.start("x", lambda emit: (emit({"node": "a"}), 42)[1], owner="u")
    t = wait(tid, "u")
    assert t["status"] == "done" and t["result"] == 42 and t["events"] == [{"node": "a"}]


def test_task_failure_is_reported_not_swallowed():
    def boom(emit):
        raise ValueError("bad")
    t = wait(tasks.start("x", boom, owner="u"), "u")
    assert t["status"] == "failed" and "ValueError: bad" in t["error"]


def test_tasks_only_visible_to_owner_and_running_guard():
    tid = tasks.start("x", lambda emit: time.sleep(0.3), owner="u")
    assert tasks.get(tid, "other") is None
    assert tasks.is_running("x", "u") and not tasks.is_running("x", "other")
    wait(tid, "u")
    assert not tasks.is_running("x", "u")


def test_llm_cache_round_trip(temp_db):
    cache = SQLiteLLMCache()
    assert cache.lookup("prompt", "model-a") is None
    cache.update("prompt", "model-a", [ChatGeneration(message=AIMessage(content="hello"))])
    hit = cache.lookup("prompt", "model-a")
    assert hit and hit[0].message.content == "hello"
    assert cache.lookup("prompt", "model-b") is None            # different model settings never share an answer
    cache.clear()
    assert cache.lookup("prompt", "model-a") is None


def test_zero_months_experience_is_kept_not_treated_as_empty():
    x = Extraction(desired_trades=[], skills=[], experience_months=0, home_locality=None, has_vehicle=None, vehicle_type=None,
                   owns_tools=None, latest_shift_end_hour=None, avoid_night_shift=False, min_monthly_wage=None,
                   evidence=[Evidence(field="experience_months", quote="I am a fresher")])
    kept, dropped = verify_extraction(x, "I am a fresher and want a delivery job")
    assert kept == {"experience_months": 0} and not dropped
