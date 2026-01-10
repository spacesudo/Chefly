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
- Multiple content types: Recipes, Tips, and Other
- Post metadata tracking (upvotes, downvotes, comment counts)
- Author-based access control

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
- **Caching**: Redis (for JWT blacklisting)
- **Validation**: Pydantic 2.12+
- **Python**: 3.13+

## Installation

### Prerequisites
- Python 3.13+
- PostgreSQL database
- Redis server (for JWT blacklisting)
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
- `POST /posts/create` - Create a new post (authenticated)
- `GET /posts/all` - Get all posts (authenticated)
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

## Database Models

### User
- User authentication and profile information
- Relationships: posts, votes, comments, follows

### Posts
- Content posts (recipes, tips, other)
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
│   ├── comments/            # Comments module
│   ├── votes/               # Voting module
│   ├── follows/             # Follow system module
│   └── db/
│       ├── main.py          # Database session management
│       ├── models.py        # SQLModel database models
│       └── redis.py         # Redis client
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
- [ ] Recipe collections/bookmarks
- [ ] Rate limiting
- [ ] Email verification

