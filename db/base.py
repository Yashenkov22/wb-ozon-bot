from sqlalchemy.ext.automap import automap_base
from sqlalchemy.engine import create_engine
from sqlalchemy.orm import sessionmaker

from config import db_url, _db_url

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy import Column, Integer, String, DATETIME, ForeignKey, Float, DateTime, TIMESTAMP, BLOB, JSON, BigInteger

# Определяем базовый класс для моделей
# Base = declarative_base()
Base = automap_base()


class Subscription(Base):
    __tablename__ = 'subscriptions'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    wb_product_limit = Column(Integer)
    ozon_product_limit = Column(Integer)
    users = relationship('User', back_populates="subscription")


class User(Base):
    __tablename__ = 'users'
    
    tg_id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    time_create = Column(TIMESTAMP(timezone=True))
    last_action = Column(String, nullable=True, default=None)
    last_action_time = Column(TIMESTAMP(timezone=True), nullable=True, default=None)
    subscription_id = Column(BigInteger, ForeignKey('subscriptions.id'), nullable=True, default=None)

    subscription = relationship(Subscription, back_populates="users")
    ozon_products = relationship("OzonProduct", back_populates="user")
    wb_punkts = relationship("WbPunkt", back_populates="user")
    wb_products = relationship("WbProduct", back_populates="user")
    jobs = relationship('UserJob', back_populates="user")


class Punkt(Base):
    __tablename__ = 'punkts'
    
    id = Column(Integer, primary_key=True, index=True)
    # lat = Column(Float)
    # lon = Column(Float)
    index = Column(BigInteger)
    city = Column(String)
    wb_zone = Column(BigInteger, default=None, nullable=True)
    ozon_zone = Column(BigInteger, default=None, nullable=True)
    time_create = Column(TIMESTAMP(timezone=True))
    user_id = Column(BigInteger, ForeignKey('users.tg_id'), nullable=True)
    
    # Связь с пользователем
    user = relationship(User, back_populates="punkts")
    # wb_products = relationship('WbProduct', back_populates="punkt")
    # ozon_products = relationship('OzonProduct', back_populates="punkt")


class WbPunkt(Base):
    __tablename__ = 'wb_punkts'
    
    id = Column(Integer, primary_key=True, index=True)
    # lat = Column(Float)
    # lon = Column(Float)
    index = Column(BigInteger)
    city = Column(String)
    zone = Column(BigInteger, default=None, nullable=True)
    time_create = Column(TIMESTAMP(timezone=True))
    user_id = Column(BigInteger, ForeignKey('users.tg_id'), nullable=True)
    
    # Связь с пользователем
    user = relationship(User, back_populates="wb_punkts")
    wb_products = relationship('WbProduct', back_populates="wb_punkt")


class OzonPunkt(Base):
    __tablename__ = 'ozon_punkts'
    
    id = Column(Integer, primary_key=True, index=True)
    # lat = Column(Float)
    # lon = Column(Float)
    index = Column(BigInteger)
    city = Column(String)
    zone = Column(BigInteger, default=None, nullable=True)
    time_create = Column(TIMESTAMP(timezone=True))
    user_id = Column(BigInteger, ForeignKey('users.tg_id'), nullable=True)
    
    # Связь с пользователем
    user = relationship(User, back_populates="ozon_punkts")
    ozon_products = relationship('OzonProduct', back_populates="ozon_punkt")


class OzonProduct(Base):
    __tablename__ = 'ozon_products'
    
    id = Column(Integer,
                primary_key=True,
                index=True)
    link = Column(String)
    short_link = Column(String)
    basic_price = Column(Float)
    start_price = Column(Float)
    actual_price = Column(Float)
    sale = Column(Float)
    # percent = Column(Integer)
    name = Column(String,
                  nullable=True,
                  default=None)
    # expected_price = Column(Float)
    # username = Column(String, nullable=True)
    # first_name = Column(String, nullable=True)
    # last_name = Column(String, nullable=True)
    time_create = Column(TIMESTAMP(timezone=True))
    user_id = Column(BigInteger, ForeignKey('users.tg_id'))
    ozon_punkt_id = Column(Integer, ForeignKey('ozon_punkts.id', ondelete='SET NULL'), nullable=True)
    
    # Связь с пользователем
    user = relationship(User, back_populates="ozon_products")
    ozon_punkt = relationship(OzonPunkt, back_populates="ozon_products", passive_deletes=True)



class WbProduct(Base):
    __tablename__ = 'wb_products'
    
    id = Column(Integer,
                primary_key=True,
                index=True)
    link = Column(String)
    short_link = Column(String)
    start_price = Column(Float)
    actual_price = Column(Float)
    sale = Column(Float)
    name = Column(String,
                  nullable=True,
                  default=None)
    time_create = Column(TIMESTAMP(timezone=True))
    user_id = Column(BigInteger, ForeignKey('users.tg_id'))
    wb_punkt_id = Column(Integer, ForeignKey('wb_punkts.id', ondelete='SET NULL'), nullable=True)

    user = relationship(User, back_populates="wb_products")
    wb_punkt = relationship(WbPunkt, back_populates="wb_products", passive_deletes=True)



class UserJob(Base):
    __tablename__ = 'user_job'
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String)
    user_id = Column(BigInteger, ForeignKey('users.tg_id'))
    product_id = Column(Integer)
    product_marker = Column(String)

    user = relationship(User, back_populates="jobs")


# Создаем асинхронный движок и сессию
# DATABASE_URL = "sqlite+aiosqlite:///test.db"

sync_engine = create_engine(_db_url, echo=True)



# Base.prepare(engine, reflect=True)
Base.prepare(autoload_with=sync_engine)
# Base.metadata.reflect(bind=sync_engine)

engine = create_async_engine(db_url, echo=True)
session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
# AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def get_session():
    async with session() as _session:
            yield _session

# Base = automap_base()

# engine = create_engine(db_url,
#                        echo=True)

# # Base.prepare(engine, reflect=True)
# Base.prepare(autoload_with=engine)

# session = sessionmaker(engine, expire_on_commit=False)