from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, UniqueConstraint, text
import sqlalchemy.dialects.postgresql as pg
from sqlmodel import Column, Field, Relationship, SQLModel

class VoteType(str, Enum):
    UPVOTE = "upvote"
    DOWNVOTE = "downvote"

class CommunityRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"

class JoinRequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class Follows(SQLModel, table=True):
    __tablename__ = "follows"
    __table_args__ = (UniqueConstraint("follower_id", "following_id", name="unique_follower_following"),)
    id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        default_factory=uuid4
    )
    follower_id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    )
    follower: "User" = Relationship(back_populates="following", sa_relationship_kwargs={"foreign_keys": "Follows.follower_id"})
    following_id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    )
    following: "User" = Relationship(back_populates="followers", sa_relationship_kwargs={"foreign_keys": "Follows.following_id"})
    
    created_at: datetime = Field(
        sa_column=Column(pg.TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True),
        default_factory=datetime.now
    )    
    
class Posts(SQLModel, table=True):
    __tablename__ = "posts"
    id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        default_factory=uuid4
    )
    title: str = Field(sa_column=Column(pg.VARCHAR(255), nullable=False, index=True))
    content: str = Field(sa_column=Column(pg.TEXT, nullable=False))
    created_at: datetime = Field(
        sa_column=Column(pg.TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
        default_factory=datetime.now
    )
    updated_at: datetime = Field(
        sa_column=Column(pg.TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
        default_factory=datetime.now
    )
    author_id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    )
    author: "User" = Relationship(back_populates="posts")
    community_id: Optional[UUID] = Field(
        sa_column=Column(pg.UUID(as_uuid=True), ForeignKey("communities.id"), nullable=True, index=True),
        default=None
    )
    votes: List["Votes"] = Relationship(back_populates="post")
    comments: List["Comments"] = Relationship(back_populates="post")
    bookmarks: List["Bookmark"] = Relationship(back_populates="post")
    upvote_count: int = Field(sa_column=Column(pg.INTEGER, nullable=True, server_default="0", index=True), default=0)
    downvote_count: int = Field(sa_column=Column(pg.INTEGER, nullable=True, server_default="0", index=True), default=0)
    comment_count: int = Field(sa_column=Column(pg.INTEGER, nullable=True, server_default="0", index=True), default=0)
    
class User(SQLModel, table=True):
    __tablename__ = "users"
    id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        default_factory=uuid4
    )
    first_name: str = Field(sa_column=Column(pg.VARCHAR(100), nullable=False, index=True))
    last_name: str = Field(sa_column=Column(pg.VARCHAR(100), nullable=False, index=True))
    username: str = Field(sa_column=Column(pg.VARCHAR(50), nullable=False, unique=True, index=True))
    email: str = Field(sa_column=Column(pg.VARCHAR(255), nullable=False, unique=True, index=True))
    hashed_password: str = Field(sa_column=Column(pg.VARCHAR(255), nullable=False), exclude=True)
    is_verified: bool = Field(sa_column=Column(pg.BOOLEAN, nullable=False, server_default="false"), default=False)
    created_at: datetime = Field(
        sa_column=Column(pg.TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True),
        default_factory=datetime.now
    )
    updated_at: datetime = Field(
        sa_column=Column(pg.TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True),
        default_factory=datetime.now
    )
    posts: List["Posts"] = Relationship(back_populates="author")
    votes: List["Votes"] = Relationship(back_populates="user")
    comments: List["Comments"] = Relationship(back_populates="user")
    bookmarks: List["Bookmark"] = Relationship(back_populates="user")
    following: List["Follows"] = Relationship(back_populates="follower",  link_model=Follows, sa_relationship_kwargs={
            "primaryjoin": "User.id == Follows.follower_id",
            "secondaryjoin": "User.id == Follows.following_id"
        })
    followers: List["Follows"] = Relationship(back_populates="following",  link_model=Follows, sa_relationship_kwargs={
            "primaryjoin": "User.id == Follows.following_id",
            "secondaryjoin": "User.id == Follows.follower_id"
        })
    
    following_count: int = Field(sa_column=Column(pg.INTEGER, nullable=True, server_default="0", index=True), default=0)
    followers_count: int = Field(sa_column=Column(pg.INTEGER, nullable=True, server_default="0", index=True), default=0)
    
class Votes(SQLModel, table=True):
    __tablename__ = "votes"
    __table_args__ = (UniqueConstraint("post_id", "user_id", name="unique_user_post_vote"),)
    id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        default_factory=uuid4
    )
    post_id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), ForeignKey("posts.id"), nullable=False, index=True)
    )
    post: "Posts" = Relationship(back_populates="votes")
    user_id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    )
    user: "User" = Relationship(back_populates="votes")
    vote_type: VoteType = Field(
        sa_column=Column(pg.ENUM(VoteType, name="vote_type", create_type=True), nullable=False, index=True)
    )
    created_at: datetime = Field(
        sa_column=Column(pg.TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True),
        default_factory=datetime.now
    )
    
class Comments(SQLModel, table=True):
    __tablename__ = "comments"
    id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        default_factory=uuid4
    )
    post_id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), ForeignKey("posts.id"), nullable=False, index=True)
    )
    post: "Posts" = Relationship(back_populates="comments")
    user_id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    )
    user: "User" = Relationship(back_populates="comments")
    content: str = Field(sa_column=Column(pg.TEXT, nullable=False))
    parent_id: Optional[UUID] = Field(
        sa_column=Column(pg.UUID(as_uuid=True), ForeignKey("comments.id"), nullable=True, index=True),
        default=None
    )
    parent: Optional["Comments"] = Relationship(
        back_populates="replies",
        sa_relationship_kwargs={"remote_side": "Comments.id"}
    )
    replies: List["Comments"] = Relationship(back_populates="parent")
    is_deleted: bool = Field(sa_column=Column(pg.BOOLEAN, nullable=False, server_default="false", index=True), default=False)
    created_at: datetime = Field(
        sa_column=Column(pg.TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True),
        default_factory=datetime.now
    )
    updated_at: datetime = Field(
        sa_column=Column(pg.TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True),
        default_factory=datetime.now
    )
    

class Bookmark(SQLModel, table=True):
    __tablename__ = "bookmarks"
    __table_args__ = (UniqueConstraint("user_id", "post_id", name="unique_user_post_bookmark"),)
    id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        default_factory=uuid4,
    )
    post_id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), ForeignKey("posts.id"), nullable=False, index=True)
    )
    post: "Posts" = Relationship(back_populates="bookmarks")
    user_id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    )
    user: "User" = Relationship(back_populates="bookmarks")
    created_at: datetime = Field(
        sa_column=Column(pg.TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True),
        default_factory=datetime.now,
    )


class Tag(SQLModel, table=True):
    __tablename__ = "tags"
    id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        default_factory=uuid4
    )
    name: str = Field(sa_column=Column(pg.VARCHAR(30), nullable=False, unique=True, index=True))
    post_count: int = Field(sa_column=Column(pg.INTEGER, nullable=False, server_default="0", index=True), default=0)
    created_at: datetime = Field(
        sa_column=Column(pg.TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
        default_factory=datetime.now
    )


class PostTag(SQLModel, table=True):
    __tablename__ = "post_tags"
    post_id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), ForeignKey("posts.id"), primary_key=True)
    )
    tag_id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), ForeignKey("tags.id"), primary_key=True, index=True)
    )


class Community(SQLModel, table=True):
    __tablename__ = "communities"
    id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        default_factory=uuid4
    )
    name: str = Field(sa_column=Column(pg.VARCHAR(100), nullable=False, unique=True, index=True))
    description: Optional[str] = Field(sa_column=Column(pg.TEXT, nullable=True), default=None)
    is_private: bool = Field(sa_column=Column(pg.BOOLEAN, nullable=False, server_default="false", index=True), default=False)
    owner_id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    )
    members_count: int = Field(sa_column=Column(pg.INTEGER, nullable=False, server_default="0", index=True), default=0)
    created_at: datetime = Field(
        sa_column=Column(pg.TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True),
        default_factory=datetime.now
    )
    updated_at: datetime = Field(
        sa_column=Column(pg.TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
        default_factory=datetime.now
    )


class CommunityMember(SQLModel, table=True):
    __tablename__ = "community_members"
    __table_args__ = (UniqueConstraint("community_id", "user_id", name="unique_community_member"),)
    id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        default_factory=uuid4
    )
    community_id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), ForeignKey("communities.id"), nullable=False, index=True)
    )
    user_id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    )
    role: CommunityRole = Field(
        sa_column=Column(pg.ENUM(CommunityRole, name="community_role", create_type=True), nullable=False, index=True),
        default=CommunityRole.MEMBER
    )
    created_at: datetime = Field(
        sa_column=Column(pg.TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True),
        default_factory=datetime.now
    )


class CommunityJoinRequest(SQLModel, table=True):
    __tablename__ = "community_join_requests"
    __table_args__ = (UniqueConstraint("community_id", "user_id", name="unique_community_join_request"),)
    id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        default_factory=uuid4
    )
    community_id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), ForeignKey("communities.id"), nullable=False, index=True)
    )
    user_id: UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    )
    status: JoinRequestStatus = Field(
        sa_column=Column(pg.ENUM(JoinRequestStatus, name="join_request_status", create_type=True), nullable=False, index=True),
        default=JoinRequestStatus.PENDING
    )
    created_at: datetime = Field(
        sa_column=Column(pg.TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True),
        default_factory=datetime.now
    )
