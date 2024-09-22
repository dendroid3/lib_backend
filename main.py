from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from schemas import UserSchema, BookSchema, BorrowedBookSchema, PurchasedBookSchema, ReceiptSchema, MpesaSchema
from database import SessionLocal
from sqlalchemy.orm import Session
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
import httpx
import base64
from typing import List, Any
import logging
import json

app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



origins = [
    "http://localhost:5173",  # Adjust the port if your frontend runs on a different one
    "https://lib-frontend-ehrc.onrender.com",
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

class PurchasedBookModel(BaseModel):
    book_id: int
    user_id: str
    purchase_date: str
    
class ReceiptModel(BaseModel):
    book_ids: str
    user_id: str
    total_amount: int
    status: int
    mpesa_code: str
    purchase_date: str
    
class MpesaModel(BaseModel):
    checkout_request_id: str
    user_id: str
    status: int
    amount: int
    paying_phone_number: int
    receipt_number: str
    transaction_date: str

class BookToBePurchasedModel(BaseModel):
    id: int
    title: str
    isbn: str
    stock: int
    price: int
    author: str
    quantity: int

class BooksArrayModel(BaseModel):
    books_array: List[BookToBePurchasedModel]


def create_user(db: Session, user: UserSchema):
    db_user = UserSchema(username=user.username, email=user.email, id=user.id, role=user.role)
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

@app.get("/sign_in/{user_id}")
def sign_in_user(user_id: str, db: Session = Depends(get_db)):
    user = db.query(UserSchema).filter(UserSchema.id == user_id).first()
    return user

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
    return_date = datetime.now() + timedelta(days=14)
    book = db.query(BookSchema).filter(BookSchema.id == book_id).first()
    if book and book.stock > 0:
        borrowed_book = BorrowedBookSchema(book_id=book_id, user_id=user_id, borrowed_date=now.strftime("%d-%m-%Y"), return_date=return_date.strftime("%d-%m-%Y"), status=1)
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
        borrowed_book.user = db.query(UserSchema).filter(UserSchema.id == borrowed_book.user_id).first()
    return borrowed_books

@app.get("/admin/get_purchased_books")
def get_books_purchased_by_admin(db: Session = Depends(get_db)):
    purchased_books = db.query(PurchasedBookSchema).all()
    for purchased_book in purchased_books:
        purchased_book.book = db.query(BookSchema).filter(BookSchema.id == purchased_book.book_id).first()
    return purchased_books

def get_encoded_credentials(consumer_key: str, consumer_secret: str) -> str:
    credentials = f"{consumer_key}:{consumer_secret}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
    return encoded_credentials

async def initiate_stk_push(token: str, amount: int, phone_number: str, message: str):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    passkey = 'bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919'
    data_to_encode = '174379' + passkey + timestamp
    password = base64.b64encode(data_to_encode.encode('utf-8')).decode('utf-8')
    # password = "MTc0Mzc5YmZiMjc5ZjlhYTliZGJjZjE1OGU5N2RkNzFhNDY3Y2QyZTBjODkzMDU5YjEwZjc4ZTZiNzJhZGExZWQyYzkxOTIwMjQwOTIxMTkwMDEx"

    # password = base64.b64encode(data_to_encode.encode('utf-8')).decode('utf-8')
    # password = "MTc0Mzc5YmZiMjc5ZjlhYTliZGJjZjE1OGU5N2RkNzFhNDY3Y2QyZTBjODkzMDU5YjEwZjc4ZTZiNzJhZGExZWQyYzkxOTIwMjQwOTIxMTkwMDEx"


    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "BusinessShortCode": 174379,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone_number,  # The phone number initiating the payment
        "PartyB": 174379,  # The Business Shortcode receiving the payment
        "PhoneNumber": phone_number,
        "CallBackURL": 'https://b317-41-89-227-171.ngrok-free.app/api/trans',
        "AccountReference": message,  # Can be any identifier for the transaction
        "TransactionDesc": message
    }
    stk_push_url = 'https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest'

    async with httpx.AsyncClient() as client:
        response = await client.post(stk_push_url, headers=headers, json=payload)
        
    return response.json()

@app.post("/books/purchase/{user_id}/{phone_number}/{total_amount}")
async def purchase_book(user_id: str, phone_number: int, books_array: BooksArrayModel, total_amount: int ,db: Session = Depends(get_db)):
    # return books_array
    # return total_amount
    now = datetime.now()
    books_ids = ''
    total_amount = 0
    # Reduce stock of purchased books
    for book_to_purchase in books_array.books_array:
        # return book_to_purchase
        book = db.query(BookSchema).filter(BookSchema.id == book_to_purchase.id).first()
        if book and book.stock > book_to_purchase.quantity:
            purchased_book = PurchasedBookSchema(book_id=book_to_purchase.id, user_id=user_id, quantity=book_to_purchase.id, purchase_date=now.strftime("%d-%m-%Y"))
            book.stock -= 1
            db.add(purchased_book)
            db.commit()
            books_ids = books_ids + str(book_to_purchase.id) + "_"
            total_amount += (book_to_purchase.quantity * book.price)
    
    # Create receipt
    receipt = ReceiptSchema(book_ids=books_ids, user_id=user_id, total_amount=total_amount, status=1, mpesa_code='', purchase_date=now.strftime("%d-%m-%Y"))
    db.add(receipt)
    db.commit()
    # return receipt
    
    # Request Mpesa
        # Request Auth
    mpesa_auth_url = 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
    mpesa_customer_key = 'zmDTtXkhe4diI75DwTHrfGai11MgVvkx'
    mpesa_customer_secret = 'onNX4p5OrApTaHRj'
    headers = {
        "Authorization": f"Basic {get_encoded_credentials(mpesa_customer_key, mpesa_customer_secret)}"
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(mpesa_auth_url, headers=headers)

    if response.status_code == 200:
        token_data = response.json()
        
        # send deposit request
        token = token_data["access_token"]

        mpesa_response = await initiate_stk_push(token, total_amount, phone_number, "Payment")

        mpesa_record = MpesaSchema(checkout_request_id=mpesa_response['CheckoutRequestID'], user_id=user_id, status=1, amount=total_amount, paying_phone_number=phone_number, receipt_number=receipt.id, transaction_date=datetime.now().strftime("%Y%m%d%H%M%S"))
        db.add(mpesa_record)
        db.commit()

        return mpesa_response
    else:
        raise HTTPException(status_code=response.status_code, detail="Failed to fetch token")

@app.get("/user/get_receipts/{user_id}")
async def get_receipts(user_id: str, db: Session = Depends(get_db)):
    receipts = db.query(ReceiptSchema).filter(ReceiptSchema.user_id == user_id).all()
    return receipts

@app.get("/user/pay_receipt/{receipt_id}/{phone_number}")
async def pay_receipt(receipt_id: int, phone_number: int, db: Session = Depends(get_db), request: Request = None):
  
    receipt = db.query(ReceiptSchema).filter(ReceiptSchema.id == receipt_id).first()
    # Request Mpesa
        # Request Auth
    mpesa_auth_url = 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
    mpesa_customer_key = 'zmDTtXkhe4diI75DwTHrfGai11MgVvkx'
    mpesa_customer_secret = 'onNX4p5OrApTaHRj'
    headers = {
        "Authorization": f"Basic {get_encoded_credentials(mpesa_customer_key, mpesa_customer_secret)}"
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(mpesa_auth_url, headers=headers)
    if response.status_code == 200:
        token_data = response.json()
        
        # send deposit request
        token = token_data["access_token"]

        mpesa_response = await initiate_stk_push(token, receipt.total_amount, phone_number, "Payment")

        if mpesa_response['ResponseDescription']:
            mpesa_record = MpesaSchema(checkout_request_id=mpesa_response['CheckoutRequestID'], user_id=receipt.user_id, status=1, amount=receipt.total_amount, paying_phone_number=phone_number, receipt_number=receipt.id, transaction_date=datetime.now().strftime("%Y%m%d%H%M%S"))
            db.add(mpesa_record)
            db.commit()
            return mpesa_response['ResponseDescription']

        return mpesa_response['errorMessage']
    else:
        raise HTTPException(status_code=response.status_code, detail="Failed to fetch token")

@app.get("/admin/get_receipts")
def admin_get_all_receipts(db: Session = Depends(get_db)):
    receipts = db.query(ReceiptSchema).all()
    for receipt in receipts:
        books = []

        receipt.user = db.query(UserSchema).filter(UserSchema.id == receipt.user_id).first()
        books_ids = receipt.book_ids.split("_")
        for book_id in books_ids:
            book = db.query(BookSchema).filter(BookSchema.id == book_id).first()
            if book:
                books.append(book.title + " by " + book.author)

        receipt.books = books
    return receipts


# Define a model for the callback metadata item
class CallbackItem(BaseModel):
    Name: str
    Value: Any

# Define a model for the callback metadata
class CallbackMetadata(BaseModel):
    Item: List[CallbackItem]

# Define a model for the stkCallback
class StkCallback(BaseModel):
    MerchantRequestID: str
    CheckoutRequestID: str
    ResultCode: int
    ResultDesc: str
    CallbackMetadata: CallbackMetadata

# Model for Body
class Body(BaseModel):
    stkCallback: StkCallback

# The top-level model
class Payload(BaseModel):
    Body: Body

@app.post('/transaction_call_back')
async def record_mpesa_transaction_complete(payload: Payload, db: Session = Depends(get_db), request: Request = None):

    logger.info(f"Request TURL: {request.url}")

    body = await request.body()  # Get the request body
    
    try:
        body_json = json.loads(body.decode('utf-8'))  # Parse body as JSON
        logger.info(f"Request body (JSON): {json.dumps(body_json, indent=4)}")  # Log the JSON body pretty-printed
    except json.JSONDecodeError:
        logger.warning("Request body is not valid JSON")  # Log if the body is not valid JSON

    logger.info(f"Request URL: {request.url}")
    logger.info(f"Request method: {request.method}")

    return
    # Deconstruct the payload
    # stk_callback = payload.Body.stkCallback
    # checkout_request_id = stk_callback.CheckoutRequestID
    # result_code = stk_callback.ResultCode
    
    # # Update mpesa record
    # mpesa_record = db.query(MpesaSchema).filter(MpesaSchema.checkout_request_id == checkout_request_id).first()
    # if mpesa_record is None:
    #     return
    
    # if result_code > 0:
    #     mpesa_record.status = 2
    #     db.commit()
    #     return
    
    # mpesa_record.status = 3
    # db.commit()

    # # Update receipt 
    # receipt = db.query(ReceiptSchema).filter(ReceiptSchema.id == mpesa_record.receipt_number).first()
    # receipt.status = 2
    # db.commit()

    # return receipt

@app.get('/book/mark_returned/{borrowed_book_id}')
def mark_book_returned(borrowed_book_id: int, db: Session = Depends(get_db)):
    borrowed_book = db.query(BorrowedBookSchema).filter(BorrowedBookSchema.id == borrowed_book_id).first()
    borrowed_book.status = 2
    db.commit()

    book = db.query(BookSchema).filter(BookSchema.id == borrowed_book.book_id).first()
    book.stock += 1
    db.commit()

    return "Book returned successfully"