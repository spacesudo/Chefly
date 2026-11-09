# ChefLy

A modern, asynchronous social media platform API for cooking recipe sharing, voting, and community engagement. Built with FastAPI, PostgreSQL, and SQLModel.

## Features

### Authentication & Authorization
- User registration and login
- JWT-based authentication (access & refresh tokens)
- Token blacklisting with Redis
- Password hashing with bcrypt
- Secure token validation

### Posts
- Create, read, update, and delete posts
- Free-form hashtags (up to 10 per post) with a suggested starter list, trending tags and tag search
- Post metadata tracking (upvotes, downvotes, comment counts)
- Author-based access control
- Chronological public feed (`GET /posts/feed`)
- Following-only feed with fallback to the public feed (`GET /posts/following-feed`)
- **FYP recommendation engine** (`api/posts/algorithm.py`) — interaction-weighted, Redis-backed personalized feed logic

### Comments
- Nested comment replies (unlimited depth)
- Create, edit, and delete comments
- Soft deletion support
- Recursive reply tree structure
- Comment threading

### Voting System
- Upvote and downvote posts
- One vote per user per post (unique constraint)
- Vote type toggling (switch between upvote/downvote)
- Real-time vote count updates
- Vote history tracking

### Social Features
- Follow/unfollow users
- View followers and following lists
- Follow status checking
- Follower/following counts
- Username-based follower queries

## Tech Stack

- **Framework**: FastAPI 0.126+
- **Database**: PostgreSQL (with asyncpg driver)
- **ORM**: SQLModel 0.0.27+
- **Migrations**: Alembic (async support)
- **Authentication**: JWT (PyJWT)
- **Password Hashing**: bcrypt
- **Caching & ranking**: Redis (JWT blacklisting, FYP interaction scores, and post rankings)
- **Validation**: Pydantic 2.12+
- **Python**: 3.13+

## Installation

### Prerequisites
- Python 3.13+
- PostgreSQL database
- Redis server (JWT blacklisting and FYP recommendation data)
- `uv` package manager (recommended) or `pip`

### Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd chefly
   ```

2. **Install dependencies**
   ```bash
   uv sync
   # or
   pip install -e .
   ```

3. **Configure environment variables**
   Create a `.env` file in the root directory:
   ```env
   DB_URL=postgresql+asyncpg://user:password@host:port/database?ssl=require
   JWT_SECRET=your-secret-key-here
   JWT_ALGORITHM=HS256
   JWT_ACCESS_EXPIRY=43200
   JWT_REFRESH_EXPIRY=172800
   REDIS_HOST=localhost
   REDIS_PORT=6379
   REDIS_DB=0
   ```

4. **Run database migrations**
   ```bash
   alembic upgrade head
   ```

5. **Start the server**
   ```bash
   uvicorn main:app --reload
   # or
   python -m uvicorn main:app --reload
   ```

## API Documentation

Once the server is running, access the interactive API documentation:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Endpoints

### Authentication (`/auth`)
- `POST /auth/signup` - Register a new user
- `POST /auth/login` - Login and get access/refresh tokens
- `POST /auth/refresh` - Refresh access token
- `POST /auth/logout` - Logout (blacklist token)

### Posts (`/posts`)
- `POST /posts/create` - Create a new post (authenticated). Body: `title`, `content`, `tags` (e.g. `["#Meal Prep", "vegan"]`)
- `GET /posts/all` - Get all posts (authenticated)
- `GET /posts/feed` - Public chronological feed sorted by recency and upvotes
- `GET /posts/following-feed` - Posts from users you follow (authenticated; falls back to `/feed` if empty)
- `GET /posts/fyp` - Personalized For You feed based on interaction history (authenticated)
- `GET /posts/{post_id}` - Get a specific post (authenticated)
- `PUT /posts/{post_id}` - Update a post (authenticated, author only)
- `DELETE /posts/{post_id}` - Delete a post (authenticated, author only)

### Comments (`/comments`)
- `POST /comments/create` - Create a comment or reply (authenticated)
- `GET /comments/post/{post_id}` - Get all comments for a post (authenticated)
- `GET /comments/{comment_id}` - Get a specific comment with replies (authenticated)
- `PUT /comments/{comment_id}` - Edit a comment (authenticated, author only)
- `DELETE /comments/{comment_id}` - Delete a comment (authenticated, author only)

### Votes (`/votes`)
- `POST /votes/create` - Create or update a vote (authenticated)
- `GET /votes/{vote_id}` - Get a specific vote (authenticated)
- `GET /votes/post/{post_id}` - Get all votes for a post (authenticated)
- `GET /votes/user/{user_id}` - Get all votes by a user (authenticated)

### Follows (`/follows`)
- `POST /follows/users/{user_id}/follow` - Follow a user (authenticated)
- `DELETE /follows/users/{user_id}/follow` - Unfollow a user (authenticated)
- `GET /follows/users/{user_id}/followers` - Get user's followers (public)
- `GET /follows/users/{user_id}/following` - Get users that a user follows (public)
- `GET /follows/users/{user_id}/follow-status` - Check follow status (authenticated)
- `GET /follows/users/{user_id}/followers-count` - Get follower count (public)
- `GET /follows/users/{user_id}/following-count` - Get following count (public)
- `GET /follows/users/{user_id}/followers-usernames` - Get follower usernames (public)
- `GET /follows/users/{user_id}/following-usernames` - Get following usernames (public)

All post responses include a `tags` list. `PUT /posts/{post_id}` accepts `tags` to replace a post's tags (`[]` clears them; omit to leave unchanged).

### Tags (`/tags`)
Tags are normalized: lowercased, `#` stripped, spaces/underscores become `-`, other symbols removed (`"#Meal Prep"` → `meal-prep`). Max 10 tags per post, 30 characters each.

- `GET /tags/suggested` - Starter tags (recipe, tip, baking, vegan, ...) followed by popular user tags (public)
- `GET /tags/trending` - Most used tags on public posts in the last `days` (default 7), falls back to all-time popular (public)
- `GET /tags/search?q=` - Prefix search for autocomplete (public)
- `GET /tags/{name}/posts` - Posts with a tag, newest first (authenticated; respects private communities)

### Bookmarks (`/bookmarks`)
- `GET /bookmarks/` - Get your bookmarked posts, newest first (authenticated; `limit`/`offset`)
- `POST /bookmarks/posts/{post_id}` - Bookmark a post (authenticated; idempotent)
- `DELETE /bookmarks/posts/{post_id}` - Remove a bookmark (authenticated)
- `GET /bookmarks/posts/{post_id}/status` - Check whether you bookmarked a post (authenticated)

### Communities (`/communities`)
All community endpoints are authenticated. Roles: `owner` (creator) > `admin` > `member`.

- `POST /communities/` - Create a community (`name`, `description`, `is_private`); creator becomes owner
- `GET /communities/` - List/search communities (`q`, `limit`, `offset`), sorted by members count
- `GET /communities/me` - Communities you belong to, with your role
- `GET /communities/{community_id}` - Community details (includes `my_role`)
- `PUT /communities/{community_id}` - Edit name/description/privacy (owner/admin)
- `DELETE /communities/{community_id}` - Delete community and its posts (owner)
- `POST /communities/{community_id}/join` - Join a public community, or send a join request to a private one
- `POST /communities/{community_id}/leave` - Leave a community (owner cannot leave)
- `GET /communities/{community_id}/members` - List members (members only if private)
- `POST /communities/{community_id}/members` - Add a user directly by `user_id` (owner/admin)
- `DELETE /communities/{community_id}/members/{user_id}` - Remove a member (owner/admin; only owner can remove admins)
- `PUT /communities/{community_id}/members/{user_id}/role` - Set role to `admin`/`member` (owner)
- `GET /communities/{community_id}/requests` - Pending join requests (owner/admin)
- `POST /communities/{community_id}/requests/{request_id}/approve` - Approve a join request (owner/admin)
- `POST /communities/{community_id}/requests/{request_id}/reject` - Reject a join request (owner/admin)
- `POST /communities/{community_id}/posts` - Create a post in the community (members)
- `GET /communities/{community_id}/posts` - Community posts, newest first (members only if private)
- `DELETE /communities/{community_id}/posts/{post_id}` - Delete a post (author or owner/admin)

Community posts live in the `posts` table (`community_id`), so replies use `POST /comments/create` and voting/bookmarking work as normal. Replying requires membership. Posts in private communities are hidden from `/posts/feed` and only appear in `/posts/all`, `/posts/following-feed`, `/posts/fyp`, and bookmarks for members.

## FYP Recommendation Algorithm

Personalized “For You” feed logic lives in `api/posts/algorithm.py`. It uses Redis as an ephemeral scoring layer on top of PostgreSQL for post retrieval.

### How it works

1. **Record interactions** — Votes, comments, and follows/unfollows automatically call `safe_record_interaction()` after a successful DB write. Each event applies a weighted score.
2. **Cold start** — Users with no interaction history receive popular posts (highest `upvote_count` from PostgreSQL).
3. **Personalized feed** — Users with history get:
   - Unseen posts from **preferred authors** (ranked by cumulative interaction weight)
   - Unseen posts carrying the user's **preferred tags** (top 10 positively scored tags)
   - Backfill from the **global post leaderboard** (`fyp:ranked_posts` in Redis)
   - Fallback to popular posts if Redis/SQL return nothing

### Interaction weights

| Interaction type | Weight |
|------------------|--------|
| `upvotes`        | +1     |
| `downvotes`      | -1     |
| `comments`       | +5     |
| `follows`        | +10    |
| `unfollows`      | -10    |
| `profile_view`   | +3     |
| `bookmarks`      | +7     |
| `unbookmarks`    | -7     |
| *(unknown)*      | +0.5   |

### Redis keys

| Key | Type | Purpose |
|-----|------|---------|
| `user:{user_id}:interactions` | Hash | Per-user post interaction scores (7-day TTL) |
| `user:{user_id}:preferred_authors` | Sorted set | Authors the user engages with most (7-day TTL) |
| `user:{user_id}:preferred_tags` | Sorted set | Tags on posts the user engages with, same weights (7-day TTL) |
| `user:{user_id}:viewed_posts` | Set | Posts already surfaced to the user |
| `fyp:ranked_posts` | Sorted set | Global post ranking by aggregate interaction score |

### Programmatic usage

```python
from uuid import UUID
from api.db.main import get_session
from api.db.redis import redis_client
from api.posts.algorithm import safe_record_interaction, get_fyp_recommendations

# Manual interaction recording (services use safe_record_interaction automatically)
await safe_record_interaction(
    user_id=user_id,
    post_id=post_id,
    interaction_type="upvotes",  # or downvotes, comments, follows, ...
    author_id=post.author_id,
)

# Fetch recommendations
async for session in get_session():
    posts = await get_fyp_recommendations(
        redis=redis_client,
        session=session,
        user_id=user_id,
        limit=20,
        offset=0,
    )
```

Interaction recording is best-effort: if Redis is unavailable, the API request still succeeds and a warning is logged.

## Database Models

### User
- User authentication and profile information
- Relationships: posts, votes, comments, follows

### Posts
- Content posts, tagged via `Tag` / `PostTag` (many-to-many; `Tag.post_count` kept in sync)
- Tracks: upvote_count, downvote_count, comment_count
- Author relationship

### Comments
- Nested comment system with parent_id
- Soft deletion support (is_deleted)
- Relationships: user, post, parent comment, replies

### Votes
- Upvote/downvote system
- Unique constraint: one vote per user per post
- Relationships: user, post

### Communities
- `Community`: name (unique), description, is_private, owner, members_count
- `CommunityMember`: user membership with role (owner/admin/member); one per user per community
- `CommunityJoinRequest`: pending/approved/rejected requests for private communities
- Posts optionally belong to a community via `community_id`

### Follows
- User following relationships
- Unique constraint: one follow per user pair
- Tracks follower_count and following_count on User model

## Authentication Flow

1. **Signup**: User registers with email, username, and password
2. **Login**: User receives access token (short-lived) and refresh token (long-lived)
3. **API Requests**: Include access token in Authorization header: `Bearer <token>`
4. **Token Refresh**: Use refresh token to get new access token when expired
5. **Logout**: Token is blacklisted in Redis

## Project Structure

```
chefly/
├── api/
│   ├── __init__.py          # FastAPI app initialization
│   ├── config.py            # Application settings
│   ├── auth/                # Authentication module
│   │   ├── routes.py        # Auth endpoints
│   │   ├── service.py       # Auth business logic
│   │   ├── schemas.py       # Auth Pydantic models
│   │   ├── utils.py         # JWT & password utilities
│   │   └── dependencies.py  # Token validation
│   ├── posts/               # Posts module
│   │   ├── routes.py        # Post & feed endpoints
│   │   ├── service.py       # Post business logic
│   │   ├── schemas.py       # Post Pydantic models
│   │   └── algorithm.py     # FYP recommendation engine (Redis + SQL)
│   ├── comments/            # Comments module
│   ├── votes/               # Voting module
│   ├── follows/             # Follow system module
│   ├── bookmarks/           # Bookmarks module
│   ├── tags/                # Tags: normalization, starter list, trending/search
│   ├── communities/         # Communities, membership, join requests
│   │   └── access.py        # Shared visibility/membership rules
│   └── db/
│       ├── main.py          # Database session management
│       ├── models.py        # SQLModel database models
│       └── redis.py         # Shared async Redis client (decode_responses=True)
├── migrations/              # Alembic migrations
├── main.py                  # Application entry point
└── pyproject.toml           # Project dependencies
```

## Development

### Running Migrations

Create a new migration:
```bash
alembic revision --autogenerate -m "description"
```

Apply migrations:
```bash
alembic upgrade head
```

Rollback:
```bash
alembic downgrade -1
```

### Code Style
- Follow PEP 8
- Use type hints
- Async/await for all database operations

## Security Features

- Password hashing with bcrypt (truncated to 72 bytes)
- JWT token validation
- Token blacklisting with Redis
- Ephemeral FYP scores in Redis (TTL-backed; stores user/post UUIDs only)
- Unique constraints on votes and follows
- Author-based access control
- Input validation with Pydantic

## Error Handling

The API uses standard HTTP status codes:
- `200` - Success
- `201` - Created
- `400` - Bad Request
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `500` - Internal Server Error

## License

See LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Future Enhancements

- [ ] Recipe ingredient and instruction parsing
- [ ] Image upload support
- [ ] Search functionality
- [ ] Notifications system
- [ ] User profiles and bio
- [x] Bookmarks
- [ ] Recipe collections
- [ ] Rate limiting
- [ ] Email verification

