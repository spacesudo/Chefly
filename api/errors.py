"""Application errors and the handlers that render every error response in one shape:

    {"error_code": "post_not_found", "message": "Post not found", "resolution": "Check the post ID; it may have been deleted"}

Raise a ChefLyException subclass anywhere; pass `message=` / `resolution=` to override the defaults for one call.
"""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.config import Config


class ChefLyException(Exception):
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "internal_error"
    message: str = "Something went wrong"
    resolution: str = "Please try again later. If the problem continues, contact support"

    def __init__(self, message: str | None = None, resolution: str | None = None):
        self.message = message or self.message
        self.resolution = resolution or self.resolution
        super().__init__(self.message)

    def to_dict(self) -> dict:
        return {"error_code": self.error_code, "message": self.message, "resolution": self.resolution}


def _error(name: str, status_code: int, error_code: str, message: str, resolution: str) -> type[ChefLyException]:
    return type(name, (ChefLyException,), {
        "status_code": status_code, "error_code": error_code, "message": message, "resolution": resolution,
    })


_400, _401, _403, _404, _409 = (
    status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN,
    status.HTTP_404_NOT_FOUND, status.HTTP_409_CONFLICT,
)

# General
InternalServerError = _error("InternalServerError", 500, "internal_error", ChefLyException.message, ChefLyException.resolution)
InvalidId = _error("InvalidId", _400, "invalid_id", "Invalid ID", "IDs must be valid UUIDs")

# Auth
NotAuthenticated = _error("NotAuthenticated", _401, "not_authenticated", "You are not logged in",
                          "Log in and send your access token as 'Authorization: Bearer <token>'")
InvalidToken = _error("InvalidToken", _401, "invalid_token", "Your token is invalid or has expired",
                      "Refresh your access token or log in again")
RevokedToken = _error("RevokedToken", _401, "revoked_token", "This token has been revoked",
                      "Log in again to get a new token")
AccessTokenRequired = _error("AccessTokenRequired", _401, "access_token_required", "An access token is required",
                             "Use the access_token from login, not the refresh_token")
RefreshTokenRequired = _error("RefreshTokenRequired", _401, "refresh_token_required", "A refresh token is required",
                              "Use the refresh_token from login, not the access_token")
InvalidCredentials = _error("InvalidCredentials", _401, "invalid_credentials", "Invalid email or password",
                            "Check your email and password and try again")
UserAlreadyExists = _error("UserAlreadyExists", _409, "user_already_exists", "An account with this email already exists",
                           "Log in instead, or sign up with a different email")
UserNotFound = _error("UserNotFound", _404, "user_not_found", "User not found",
                      "Check the user ID; the account may no longer exist")

# Posts & tags
PostNotFound = _error("PostNotFound", _404, "post_not_found", "Post not found",
                      "Check the post ID; the post may have been deleted")
NotPostAuthor = _error("NotPostAuthor", _403, "not_post_author", "You are not the author of this post",
                       "Only the author can edit or delete a post")

# Comments
CommentNotFound = _error("CommentNotFound", _404, "comment_not_found", "Comment not found",
                         "Check the comment ID; the comment may have been deleted")
ParentCommentNotFound = _error("ParentCommentNotFound", _404, "parent_comment_not_found", "The comment you're replying to doesn't exist",
                               "Refresh the thread; the comment may have been deleted")
ParentCommentMismatch = _error("ParentCommentMismatch", _400, "parent_comment_mismatch", "The comment you're replying to belongs to a different post",
                               "Reply using a comment from the same post")
NotCommentAuthor = _error("NotCommentAuthor", _403, "not_comment_author", "You are not the author of this comment",
                          "Only the author can edit or delete a comment")

# Votes
VoteNotFound = _error("VoteNotFound", _404, "vote_not_found", "Vote not found",
                      "Check the vote ID; the vote may already have been removed")
NotVoteOwner = _error("NotVoteOwner", _403, "not_vote_owner", "You can only remove your own vote",
                      "Use the ID of a vote you cast")

# Follows
CannotFollowSelf = _error("CannotFollowSelf", _400, "cannot_follow_self", "You cannot follow yourself",
                          "Follow another user instead")
AlreadyFollowing = _error("AlreadyFollowing", _409, "already_following", "You are already following this user",
                          "No action needed")
NotFollowing = _error("NotFollowing", _404, "not_following", "You are not following this user",
                      "No action needed")

# Bookmarks
BookmarkNotFound = _error("BookmarkNotFound", _404, "bookmark_not_found", "This post isn't in your bookmarks",
                          "No action needed")

# Communities
CommunityNotFound = _error("CommunityNotFound", _404, "community_not_found", "Community not found",
                           "Check the community ID; it may have been deleted")
CommunityPrivate = _error("CommunityPrivate", _403, "community_private", "This community is private",
                          "Request to join the community to see its content")
NotCommunityMember = _error("NotCommunityMember", _403, "not_community_member", "You must be a member of this community",
                            "Join the community first")
CommunityPermissionDenied = _error("CommunityPermissionDenied", _403, "community_permission_denied", "You don't have permission to do this",
                                   "Only the community owner or admins can do this")
OnlyOwnerAllowed = _error("OnlyOwnerAllowed", _403, "community_owner_only", "Only the community owner can do this",
                          "Ask the community owner")
CommunityNameTaken = _error("CommunityNameTaken", _409, "community_name_taken", "A community with this name already exists",
                            "Choose a different name")
AlreadyCommunityMember = _error("AlreadyCommunityMember", _409, "already_community_member", "Already a member of this community",
                                "No action needed")
CommunityMemberNotFound = _error("CommunityMemberNotFound", _404, "community_member_not_found", "That user is not a member of this community",
                                 "Check the user ID")
OwnerCannotLeave = _error("OwnerCannotLeave", _400, "owner_cannot_leave", "The owner cannot leave the community",
                          "Delete the community instead")
OwnerCannotBeRemoved = _error("OwnerCannotBeRemoved", _400, "owner_cannot_be_removed", "The community owner cannot be removed",
                              "Remove a different member")
OwnerRoleImmutable = _error("OwnerRoleImmutable", _400, "owner_role_immutable", "The owner's role cannot be changed",
                            "Change the role of a different member")
InvalidCommunityRole = _error("InvalidCommunityRole", _400, "invalid_community_role", "Role must be 'admin' or 'member'",
                              "Send role 'admin' or 'member'")
JoinRequestNotFound = _error("JoinRequestNotFound", _404, "join_request_not_found", "Join request not found",
                             "Refresh the pending requests list")
JoinRequestAlreadyReviewed = _error("JoinRequestAlreadyReviewed", _409, "join_request_already_reviewed", "This join request has already been reviewed",
                                    "Refresh the pending requests list")
CommunityPostNotFound = _error("CommunityPostNotFound", _404, "community_post_not_found", "Post not found in this community",
                               "Check the post and community IDs")

# Notifications
NotificationNotFound = _error("NotificationNotFound", _404, "notification_not_found", "Notification not found",
                              "Refresh your notifications")

# Chat
ConversationNotFound = _error("ConversationNotFound", _404, "conversation_not_found", "Conversation not found",
                              "Check the conversation ID; it may have been deleted")
MessageNotFound = _error("MessageNotFound", _404, "message_not_found", "Message not found",
                         "The message may have been deleted")
NotMessageSender = _error("NotMessageSender", _403, "not_message_sender", "You can only change your own messages",
                          "Edit or delete a message you sent")
CannotMessageSelf = _error("CannotMessageSelf", _400, "cannot_message_self", "You cannot message yourself",
                           "Start a conversation with another user")
EmptyMessage = _error("EmptyMessage", _400, "empty_message", "A message needs content or a shared post",
                      "Add text or attach a post")
MessageRequestNotPending = _error("MessageRequestNotPending", _400, "message_request_not_pending", "Only pending message requests can be declined",
                                  "This conversation is already in your inbox")

# Realtime
UnknownSocketMessage = _error("UnknownSocketMessage", _400, "unknown_socket_message", "Unknown message type",
                              "Use one of: ping, typing, read, send_message")
InvalidSocketMessage = _error("InvalidSocketMessage", _400, "invalid_socket_message", "Invalid message",
                              "Send a JSON object with a 'type' field and the fields that type requires")


# Fallbacks for errors raised by FastAPI/Starlette themselves (unknown route, wrong method, missing auth header, ...)
_HTTP_DEFAULTS = {
    401: ("not_authenticated", NotAuthenticated.resolution),
    403: ("forbidden", "You don't have access to this resource"),
    404: ("not_found", "Check the URL"),
    405: ("method_not_allowed", "Check the HTTP method for this endpoint"),
}


async def _chefly_handler(request: Request, exc: ChefLyException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


async def _http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # HTTPBearer rejects a missing Authorization header with 403 "Not authenticated"
    if exc.detail == "Not authenticated":
        return await _chefly_handler(request, NotAuthenticated())
    error_code, resolution = _HTTP_DEFAULTS.get(exc.status_code, ("http_error", "Check your request and try again"))
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": error_code, "message": str(exc.detail), "resolution": resolution},
        headers=getattr(exc, "headers", None),
    )


async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"field": ".".join(str(part) for part in err["loc"] if part != "body") or "body", "message": err["msg"]}
        for err in exc.errors()
    ]
    first = details[0] if details else {"field": "body", "message": "Invalid request"}
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error_code": "validation_error",
            "message": f"Invalid {first['field']}: {first['message']}",
            "resolution": "Fix the listed fields and try again",
            "details": details,
        },
    )


async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    # Starlette re-raises after this handler, so the traceback is still logged by the server
    body = InternalServerError().to_dict()
    if Config.DEBUG:
        body["debug"] = f"{type(exc).__name__}: {exc}"
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=body)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ChefLyException, _chefly_handler)
    app.add_exception_handler(StarletteHTTPException, _http_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(Exception, _unhandled_handler)
