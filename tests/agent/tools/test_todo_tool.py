# tests/agent/tools/test_todo_tool.py
import pytest
from agent.planning import PlanItem
from agent.tools.builtin.todo import TodoWriteTool


def _make_tool():
    """Create a TodoWriteTool backed by an in-memory list."""
    items: list[PlanItem] = []
    next_id_counter = [1]

    def create(content):
        item = PlanItem(id=f"todo-{next_id_counter[0]}", content=content, status="pending")
        next_id_counter[0] += 1
        items.append(item)
        return item

    def update(item_id, status, note):
        for item in items:
            if item.id == item_id:
                item.status = status
                item.note = note
                return item
        raise ValueError(f"unknown todo item: {item_id}")

    def list_items(status_filter):
        if status_filter is None:
            return list(items)
        return [i for i in items if i.status == status_filter]

    return TodoWriteTool(create_cb=create, update_cb=update, list_cb=list_items)


@pytest.mark.asyncio
async def test_create_todo():
    tool = _make_tool()
    result = await tool.execute(operation="create", content="Implement Edit tool")
    assert "todo-1" in result
    assert "status=pending" in result


@pytest.mark.asyncio
async def test_create_todo_empty_content():
    tool = _make_tool()
    result = await tool.execute(operation="create", content="")
    assert result.startswith("[Error")


@pytest.mark.asyncio
async def test_create_todo_missing_content():
    tool = _make_tool()
    result = await tool.execute(operation="create")
    assert result.startswith("[Error")


@pytest.mark.asyncio
async def test_update_todo_status():
    tool = _make_tool()
    await tool.execute(operation="create", content="Task 1")
    result = await tool.execute(operation="update", id="todo-1", status="in_progress")
    assert "status=in_progress" in result


@pytest.mark.asyncio
async def test_update_todo_invalid_status():
    tool = _make_tool()
    await tool.execute(operation="create", content="Task 1")
    result = await tool.execute(operation="update", id="todo-1", status="unknown")
    assert result.startswith("[Error: invalid status")


@pytest.mark.asyncio
async def test_update_todo_unknown_id():
    tool = _make_tool()
    result = await tool.execute(operation="update", id="nonexistent", status="completed")
    assert "unknown todo item" in result


@pytest.mark.asyncio
async def test_update_todo_missing_id():
    tool = _make_tool()
    result = await tool.execute(operation="update", status="completed")
    assert result.startswith("[Error")


@pytest.mark.asyncio
async def test_list_all_todos():
    tool = _make_tool()
    await tool.execute(operation="create", content="Task 1")
    await tool.execute(operation="create", content="Task 2")
    result = await tool.execute(operation="list")
    assert "Task 1" in result
    assert "Task 2" in result
    assert "2 todo item(s)" in result


@pytest.mark.asyncio
async def test_list_filter_by_status():
    tool = _make_tool()
    await tool.execute(operation="create", content="Task 1")
    await tool.execute(operation="create", content="Task 2")
    await tool.execute(operation="update", id="todo-1", status="completed")
    result = await tool.execute(operation="list", status="completed")
    assert "Task 1" in result
    assert "Task 2" not in result


@pytest.mark.asyncio
async def test_list_empty():
    tool = _make_tool()
    result = await tool.execute(operation="list")
    assert "empty" in result


@pytest.mark.asyncio
async def test_unknown_operation():
    tool = _make_tool()
    result = await tool.execute(operation="delete")
    assert result.startswith("[Error: unknown operation")
