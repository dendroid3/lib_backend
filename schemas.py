from sqlalchemy import Column, Integer, String, ForeignKey
from database import Base
from database import engine

class UserSchema(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    #1 == user, 2 == adimin
    role = Column(Integer)


class BookSchema(Base):
    __tablename__ = "books"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, unique=True, index=True)
    author = Column(String)
    isbn = Column(String, unique=True, index=True)
    stock = Column(Integer)
    price = Column(Integer)

class BorrowedBookSchema(Base):
    __tablename__ = "borrowed_books"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey("books.id"))
    user_id = Column(String, ForeignKey("users.id"))
    borrowed_date = Column(String)
    return_date = Column(String)
    # 1 == borrowed, 2 == returned
    status =  Column(Integer)
# Create the database tables if they don't exist

Base.metadata.create_all(bind=engine)
