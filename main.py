from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import JSONResponse
from schemas import UserSchema, BookSchema, BorrowedBookSchema
from database import SessionLocal
from sqlalchemy.orm import Session
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

app = FastAPI()


origins = [
    "http://localhost:5173",  # Adjust the port if your frontend runs on a different one
    "https://yourfrontenddomain.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Allows all origins from the list
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class UserModel(BaseModel):
    id: str
    username: str
    email: str
    role: int

class BookModel(BaseModel):
    title: str
    isbn: str
    stock: int
    price: int
    author: str

class BorrowedBookModel(BaseModel):
    book_id: int
    user_id: str
    borrowed_date: str
    return_date: str
    status: int
 
def create_user(db: Session, user: UserModel):
    db_user = UserModel(username=user.username, email=user.email, id=user.id, role=user.role)
    db.add(db_user)
    db.commit()
    return db_user

def create_book(db: Session, book: BookSchema):
    db_book = BookSchema(title=book.title, author=book.author, isbn=book.isbn, stock=book.stock, price=book.price)
    db.add(db_book)
    db.commit()
    return "Book created successfully"

@app.post("/register")
def register_user(user: UserModel, db: Session = Depends(get_db)):
    return create_user(db=db, user=user)

@app.post("/admin/add_book")
def add_book(book: BookModel, db: Session = Depends(get_db)):
    return create_book(db=db, book=book)

@app.get("/books/get_all")
def get_books(db: Session = Depends(get_db)):
    books = db.query(BookSchema).all()
    return books


@app.get("/books/delete/{book_id}")
def delete_book(book_id: int, db: SessionLocal = Depends(get_db)):
    book = db.query(BookSchema).filter(BookSchema.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    db.delete(book)
    db.commit()
    return {"message": "Book deleted"}

@app.get("/books/borrow/{user_id}/{book_id}")
def borrow_book(book_id: int, user_id: str, db: Session = Depends(get_db)):
    now = datetime.now()
    book = db.query(BookSchema).filter(BookSchema.id == book_id).first()
    if book and book.stock > 0:
        borrowed_book = BorrowedBookSchema(book_id=book_id, user_id=user_id, borrowed_date=now.strftime("%d-%m-%Y"), return_date=now.strftime("%d-%m-%Y"), status=1)
        book.stock -= 1
        db.add(borrowed_book)
        db.commit()
        content = {"message": "Book borrowed successfully!", "status": "success"}
        return JSONResponse(content=content, status_code=200)
    raise HTTPException(status_code=404, detail="Book not available")

@app.get("/user/get_borrowed_books/{user_id}")
def get_books_borrowed_by_user(user_id: str, db: Session = Depends(get_db)):
    borrowed_books = db.query(BorrowedBookSchema).filter(BorrowedBookSchema.user_id == user_id).all()
    for borrowed_book in borrowed_books:
        borrowed_book.book = db.query(BookSchema).filter(BookSchema.id == borrowed_book.book_id).first()
    return borrowed_books

@app.get("/admin/mark_borrowed_book_as_returned/{user_id}/{book_id}")
def mark_borrowed_book_as_returned(user_id: str, book_id: int, db: Session = Depends(get_db)):
    borrowed_book = db.query(BorrowedBookSchema).filter(BorrowedBookSchema.user_id == user_id).filter(BorrowedBookSchema.book_id == book_id).filter(BorrowedBookSchema.status == 1).first()
    borrowed_book.status = 2
    book = db.query(BookSchema).filter(BookSchema.id == book_id).first()
    book.stock += 1
    db.commit()

    return borrowed_book

@app.get("/admin/get_borrowed_books")
def get_books_borrowed_by_admin(db: Session = Depends(get_db)):
    borrowed_books = db.query(BorrowedBookSchema).all()
    for borrowed_book in borrowed_books:
        borrowed_book.book = db.query(BookSchema).filter(BookSchema.id == borrowed_book.book_id).first()
    return borrowed_books
