"""Account administration.

Admin-only. Everything here goes through `require_admin`, and the guards live
in `repo.set_user_role` rather than in the view, so the JSON path and any
future caller get them too.
"""

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app import csrf
from app import repository as repo
from app.auth import require_admin
from app.web import templates

router = APIRouter(prefix="/admin", tags=["admin"])


def _render(request: Request, *, error: str | None = None, status_code: int = 200):
    return templates.TemplateResponse(
        request,
        "admin_users.html",
        {
            "users": repo.list_users(),
            "roles": repo.ROLES,
            "changes": repo.recent_role_changes(),
            "error": error,
        },
        status_code=status_code,
    )


@router.get("/users", response_class=HTMLResponse)
def list_users(request: Request):
    require_admin(request)
    return _render(request)


@router.post("/users/{user_id}/role")
def set_role(
    request: Request,
    user_id: int,
    role: str = Form(...),
    confirm: str = Form(default=""),
    csrf_token: str = Form(default=""),
):
    actor = require_admin(request)

    # No draft to preserve here — the form is a select, not prose — so this
    # one just refuses.
    csrf.require(request, csrf_token)

    # Demoting yourself is allowed but never a click away — losing your own
    # admin rights is not something to do by accident.
    if user_id == actor.get("id") and role != "admin" and confirm != "yes":
        return _render(
            request,
            error=(
                "That would remove your own admin access. Tick the confirm box "
                "on your row if you really mean it."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        repo.set_user_role(user_id, role, actor)
    except repo.UserNotFound:
        return _render(request, error="No such account.", status_code=status.HTTP_404_NOT_FOUND)
    except repo.InvalidRole:
        return _render(
            request,
            error=f"{role!r} is not a role.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except repo.LastAdminProtected:
        return _render(
            request,
            error=(
                "That's the only admin left. Promote someone else first — an "
                "instance with no admin can't hand the role back out."
            ),
            status_code=status.HTTP_409_CONFLICT,
        )

    # Nothing to patch into the session: since 0.13.0 every request re-reads
    # the role, so the actor's next one already reflects the change.
    return RedirectResponse("/admin/users", status_code=status.HTTP_303_SEE_OTHER)
