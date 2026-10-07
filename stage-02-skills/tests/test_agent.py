"""Agent thật (create_agent + middleware) với mock model: tool trace và request snapshot."""

from langchain_core.messages import AIMessage, HumanMessage

import paths
from agent import TOOLS, build_agent, system_prompt
from observer import Observer
from tests.conftest import ScriptedChatModel


def stream_events(agent, messages):
    events, new_messages = [], []
    for mode, chunk in agent.stream({"messages": messages}, stream_mode=["updates", "custom"]):
        if mode == "custom" and chunk.get("observer"):
            events.append(chunk)
        elif mode == "updates":
            for update in chunk.values():
                if isinstance(update, dict) and update.get("messages"):
                    new_messages.extend(update["messages"])
    return events, new_messages


def test_registered_tools():
    assert [t.name for t in TOOLS] == ["list_files", "read_file", "write_file"]


def test_read_then_write_with_parallel_calls_and_missing_file(lab_dirs):
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "read_file", "args": {"path": "data/weekly_notes.md"}, "id": "r1"},
                    {"name": "read_file", "args": {"path": "data/khong-co.md"}, "id": "r2"},
                ],
            ),
            AIMessage(content="", tool_calls=[{"name": "write_file", "args": {"path": "output/summary.md", "content": "# Tóm tắt"}, "id": "w1"}]),
            AIMessage(content="Đã ghi output/summary.md"),
        ]
    )
    events, new_messages = stream_events(build_agent(model), [HumanMessage(content="Đọc data/weekly_notes.md và ghi tóm tắt vào output/summary.md.")])

    kinds = [e["event"] for e in events]
    assert kinds.count("model_request") == 3
    assert kinds.count("tool_started") == 3 and kinds.count("tool_finished") == 3
    finished = {e["data"]["tool_call_id"]: e["data"] for e in events if e["event"] == "tool_finished"}
    assert finished["r1"]["result"]["ok"] is True and "Endpoint đăng nhập" in finished["r1"]["result"]["content"]
    assert finished["r2"]["result"]["error"]["code"] == "FILE_NOT_FOUND"
    assert finished["w1"]["result"] == {"ok": True, "path": "output/summary.md", "bytes": len("# Tóm tắt".encode()), "status": "created"}
    assert (paths.WORKSPACE_DIR / "output" / "summary.md").read_text(encoding="utf-8") == "# Tóm tắt"

    requests = [e["data"] for e in events if e["event"] == "model_request"]
    assert requests[0]["system_prompt"] == system_prompt()
    assert [t["name"] for t in requests[0]["tools"]] == ["list_files", "read_file", "write_file"]
    assert requests[0]["tools"][0]["parameters"]["required"] == ["path"]
    assert requests[0]["tools"][2]["parameters"]["required"] == ["path", "content"]
    second_roles = [m["role"] for m in requests[1]["messages"]]
    assert second_roles == ["user", "assistant", "tool", "tool"]
    assert {m["tool_call_id"] for m in requests[1]["messages"] if m["role"] == "tool"} == {"r1", "r2"}
    assert new_messages[-1].content == "Đã ghi output/summary.md"


def test_skill_loaded_by_read_file_reaches_next_request_and_follow_up(lab_dirs):
    model = ScriptedChatModel(
        responses=[
            AIMessage(content="", tool_calls=[{"name": "read_file", "args": {"path": "skills/weekly-report/SKILL.md"}, "id": "s1"}]),
            AIMessage(content="Đã đọc skill."),
            AIMessage(content="Follow-up trả lời."),
        ]
    )
    agent = build_agent(model)
    observer = Observer(conversation_id="conv")
    history = [HumanMessage(content="Tạo báo cáo tuần từ data/weekly_notes.md, lưu vào output/weekly-report.md.")]

    def run_turn(run_id):
        observer.start_turn(run_id)
        events, new_messages = stream_events(agent, history)
        for event in events:
            observer.record(event["event"], event["data"])
        history.extend(new_messages)
        observer.sync_messages(history)

    run_turn("run-1")
    first, second = observer.snapshots
    assert "Phân loại từng ghi chú" not in first["system_prompt"]
    assert all("Phân loại từng ghi chú" not in str(m["content"]) for m in first["messages"])
    tool_message = second["messages"][2]
    assert tool_message["role"] == "tool" and tool_message["tool_call_id"] == "s1"
    assert "Phân loại từng ghi chú" in tool_message["content"]
    loaded = observer.inventory()["skills"]
    assert [(s["skill"], s["tool_call_id"], s["first_request"]) for s in loaded] == [("weekly-report", "s1", "Lượt 1, model call #2")]

    history.append(HumanMessage(content="Tóm tắt lại giúp anh."))
    run_turn("run-2")
    follow_up = observer.snapshots[-1]
    assert follow_up["chat_turn"] == 2
    assert any(m.get("tool_call_id") == "s1" and "Phân loại từng ghi chú" in m["content"] for m in follow_up["messages"])

    fresh = Observer(conversation_id="conv-2")
    assert fresh.inventory()["skills"] == []


def test_list_then_read_discovered_file(lab_dirs):
    model = ScriptedChatModel(
        responses=[
            AIMessage(content="", tool_calls=[{"name": "list_files", "args": {"path": "data"}, "id": "l1"}]),
            AIMessage(content="", tool_calls=[{"name": "read_file", "args": {"path": "data/weekly_notes.md"}, "id": "r1"}]),
            AIMessage(content="Đã đọc data/weekly_notes.md"),
        ]
    )
    events, _ = stream_events(build_agent(model), [HumanMessage(content="Trong data có tài liệu gì? Đọc ghi chú tuần.")])

    finished = {e["data"]["tool_call_id"]: e["data"] for e in events if e["event"] == "tool_finished"}
    listed = finished["l1"]["result"]
    assert listed["ok"] is True and listed["path"] == "data"
    assert {"name": "weekly_notes.md", "path": "data/weekly_notes.md", "type": "file"} in listed["entries"]
    assert finished["r1"]["result"]["ok"] is True
    # Model nhận kết quả list_files trước khi gọi read_file
    tool_messages = [m for m in model.received[1] if m.type == "tool"]
    assert [m.tool_call_id for m in tool_messages] == ["l1"]


def test_listing_skill_directory_does_not_load_skill(lab_dirs):
    model = ScriptedChatModel(
        responses=[
            AIMessage(content="", tool_calls=[{"name": "list_files", "args": {"path": "skills/weekly-report"}, "id": "l1"}]),
            AIMessage(content="Skill có SKILL.md và references/."),
        ]
    )
    observer = Observer(conversation_id="conv")
    history = [HumanMessage(content="Skill weekly-report gồm những file nào?")]
    observer.start_turn("run-1")
    events, new_messages = stream_events(build_agent(model), history)
    for event in events:
        observer.record(event["event"], event["data"])
    observer.sync_messages(history + new_messages)

    listed = next(e["data"]["result"] for e in events if e["event"] == "tool_finished")
    assert {"name": "SKILL.md", "path": "skills/weekly-report/SKILL.md", "type": "file"} in listed["entries"]
    assert {"name": "references", "path": "skills/weekly-report/references", "type": "directory"} in listed["entries"]
    # Chỉ read_file SKILL.md thành công mới tính là đã load skill
    assert observer.inventory() == {"skills": [], "resources": []}


def test_refund_skill_finds_policies_with_list_files_and_reads_them(lab_dirs):
    model = ScriptedChatModel(
        responses=[
            AIMessage(content="", tool_calls=[{"name": "read_file", "args": {"path": "skills/refund-policy/SKILL.md"}, "id": "s1"}]),
            AIMessage(content="", tool_calls=[{"name": "list_files", "args": {"path": "data/policies"}, "id": "l1"}]),
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "read_file", "args": {"path": "data/policies/policy-before-oct.md"}, "id": "p1"},
                    {"name": "read_file", "args": {"path": "data/policies/policy-from-oct.md"}, "id": "p2"},
                    {"name": "read_file", "args": {"path": "skills/refund-policy/references/answer-template.md"}, "id": "t1"},
                ],
            ),
            AIMessage(content="Đủ điều kiện hoàn tiền."),
        ]
    )
    observer = Observer(conversation_id="conv")
    history = [HumanMessage(content="Mua 2026-10-03, yêu cầu hoàn 2026-10-12, chưa kích hoạt. Có được hoàn tiền không?")]
    observer.start_turn("run-1")
    events, new_messages = stream_events(build_agent(model), history)
    for event in events:
        observer.record(event["event"], event["data"])
    observer.sync_messages(history + new_messages)

    finished = {e["data"]["tool_call_id"]: e["data"]["result"] for e in events if e["event"] == "tool_finished"}
    assert "Thông tin bắt buộc" in finished["s1"]["content"]
    assert [e["path"] for e in finished["l1"]["entries"]] == ["data/policies/policy-before-oct.md", "data/policies/policy-from-oct.md"]
    assert "Áp dụng cho ngày mua trước 2026-10-01" in finished["p1"]["content"]
    assert "Áp dụng cho ngày mua từ 2026-10-01" in finished["p2"]["content"]
    assert "**Căn cứ:**" in finished["t1"]["content"]
    inventory = observer.inventory()
    assert [s["skill"] for s in inventory["skills"]] == ["refund-policy"]
    # 3 read_file chạy song song: thứ tự tool message không cố định
    assert sorted(r["path"] for r in inventory["resources"]) == [
        "data/policies/policy-before-oct.md",
        "data/policies/policy-from-oct.md",
        "skills/refund-policy/references/answer-template.md",
    ]
