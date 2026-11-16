"""Administrator-only, read-only account and collection insights."""
from fastapi import APIRouter, Depends, HTTPException, Query
from .auth import require_admin
from .db import connect

router = APIRouter(prefix="/admin/users")

COUNTS = """
SELECT u.id,u.username,u.role,u.is_active,u.created_at,
 (SELECT COUNT(*) FROM collections WHERE user_id=u.id) AS board_count,
 (SELECT COUNT(*) FROM collection_items i JOIN collections c ON c.id=i.collection_id WHERE c.user_id=u.id) AS item_count,
 (SELECT COUNT(DISTINCT i.figure_id) FROM collection_items i JOIN collections c ON c.id=i.collection_id WHERE c.user_id=u.id) AS figure_count,
 (SELECT COUNT(DISTINCT f.paper_id) FROM collection_items i JOIN collections c ON c.id=i.collection_id JOIN figures f ON f.id=i.figure_id WHERE c.user_id=u.id) AS paper_count,
 (SELECT MAX(viewed_at) FROM view_history WHERE user_id=u.id) AS last_viewed_at
FROM users u
"""

@router.get("")
def users(user=Depends(require_admin)):
    with connect() as db:
        rows = [dict(row) for row in db.execute(COUNTS + " ORDER BY u.created_at DESC,u.id DESC")]
    return {"users": rows, "summary": {
        "users": len(rows), "active_users": sum(r["is_active"] for r in rows),
        "boards": sum(r["board_count"] for r in rows),
        "items": sum(r["item_count"] for r in rows),
        "figures": sum(r["figure_count"] for r in rows),
    }}

@router.get("/{uid}")
def user_detail(uid: int, collection_id: str | None = None,
                offset: int = Query(0, ge=0), limit: int = Query(24, ge=1, le=100),
                user=Depends(require_admin)):
    from .api import SELECT, deserialize
    with connect() as db:
        db.execute("BEGIN")
        account = db.execute(COUNTS + " WHERE u.id=?", (uid,)).fetchone()
        if not account:
            raise HTTPException(404, "用户不存在")
        boards = [dict(r) for r in db.execute(
            "SELECT c.id,c.name,c.updated_at,COUNT(i.id) AS count FROM collections c "
            "LEFT JOIN collection_items i ON i.collection_id=c.id WHERE c.user_id=? "
            "GROUP BY c.id ORDER BY c.updated_at DESC,c.id", (uid,))]
        if collection_id and collection_id not in {b["id"] for b in boards}:
            raise HTTPException(404, "该用户的看板不存在")
        condition = " WHERE c.user_id=?" + (" AND c.id=?" if collection_id else "")
        args = [uid] + ([collection_id] if collection_id else [])
        total = db.execute("SELECT COUNT(*) FROM collection_items i JOIN collections c ON c.id=i.collection_id" + condition, args).fetchone()[0]
        # Reuse public figure serialization; never return password/session fields.
        query = SELECT.replace("SELECT f.*", "SELECT i.id AS item_id,i.created_at AS saved_at,c.id AS collection_id,c.name AS collection_name,f.*")
        query += "JOIN collection_items i ON i.figure_id=f.id JOIN collections c ON c.id=i.collection_id" + condition
        items = [deserialize(r) for r in db.execute(query + " ORDER BY i.created_at DESC,i.id DESC LIMIT ? OFFSET ?", args + [limit, offset])]
    return {"user": dict(account), "boards": boards, "items": items, "total": total,
            "offset": offset, "limit": limit, "next_offset": offset + limit if offset + limit < total else None}
