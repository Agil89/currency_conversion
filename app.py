import asyncio
import httpx
from datetime import datetime
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.future import select
from sqlalchemy import Column, String, Float, DateTime, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql+asyncpg://user:password@db:5432/dbname"
API_URL = "https://api.freecurrencyapi.com/v1/latest?apikey=fca_live_uYBkhZetHx4W8ANppGpTYPPUEtoTCrT5dH3NfM6T"
engine = create_async_engine(DATABASE_URL, echo=True)  # Set echo=True for debugging

Base = declarative_base()

class Currency(Base):
    __tablename__ = "currencies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    code = Column(String, unique=True)
    rate = Column(Float)
    last_updated = Column(DateTime)

# Create tables asynchronously
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

# Function to Fetch Exchange Rates
async def fetch_and_save_exchange_rates():
    async with httpx.AsyncClient() as client:
        response = await client.get(API_URL)
        data = response.json()
        # Extract exchange rates from the API response
        rates = data.get("data", {})        
        # Update exchange rates in the database
        async with AsyncSession(engine) as session:
            async with session.begin():
                for code, rate in rates.items():
                    # Check if the currency already exists in the database
                    currency = await session.execute(select(Currency).filter_by(code=code))
                    currency = currency.scalar_one_or_none()
                    if currency:
                        # Update existing currency rate
                        currency.rate = rate
                        currency.last_updated = datetime.utcnow()
                    else:
                        # Create new currency entry
                        new_currency = Currency(code=code, rate=rate, last_updated=datetime.utcnow())
                        session.add(new_currency)

# Function to Retrieve Last Update Time
async def get_last_update_time():
    async with AsyncSession(engine) as session:
        async with session.begin():
            result = await session.execute(select(Currency).order_by(Currency.last_updated.desc()).limit(1))
            currency = result.scalar_one_or_none()
            if currency:
                return currency.last_updated
            else:
                return None

# Conversion Function
async def convert_currency(source_currency, target_currency, amount):
    async with AsyncSession(engine) as session:
        async with session.begin():
            # Query the database for exchange rates of the source and target currencies
            source_result = await session.execute(select(Currency).filter_by(code=source_currency))
            target_result = await session.execute(select(Currency).filter_by(code=target_currency))
            
            source_currency_obj = source_result.scalar_one_or_none()
            target_currency_obj = target_result.scalar_one_or_none()
            
            if not source_currency_obj or not target_currency_obj:
                return None  # Currency not found in the database
            
            # Perform conversion
            converted_amount = amount * (target_currency_obj.rate / source_currency_obj.rate)
            
            return converted_amount

# FastAPI Setup


app = FastAPI()

@app.on_event("startup")
async def startup_event():
    await create_tables()


# example url will be look like this:
# http://localhost:8000/update_exchange_rates
@app.get("/update_exchange_rates")
async def update_exchange_rates():
    await fetch_and_save_exchange_rates()
    return {"message": "Exchange rates updated successfully"}

# example url will be look like this:
# http://localhost:8000/last_update_time
@app.get("/last_update_time")
async def last_update_time():
    last_update = await get_last_update_time()
    return {"last_update_time": last_update}


# example url will be look like this:
# http://localhost:8000/convert_currency?source_currency=USD&target_currency=EUR&amount=100.0
@app.get("/convert_currency")
async def convert_currency_api(source_currency: str, target_currency: str, amount: float):
    result = await convert_currency(source_currency, target_currency, amount)
    return {"result": result}
