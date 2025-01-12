from sqlalchemy.ext.automap import automap_base
from sqlalchemy.engine import create_engine
from sqlalchemy.orm import sessionmaker

from config import db_url

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy import Column, Integer, String, DATETIME, ForeignKey, Float, DateTime, TIMESTAMP, BLOB, JSON

# Определяем базовый класс для моделей
Base = declarative_base()

# Определяем модель
class User(Base):
    __tablename__ = 'users'
    
    tg_id = Column(Integer, primary_key=True, index=True)
    # tg_id = Column(Integer)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    time_create = Column(TIMESTAMP(timezone=True))

    ozon_products = relationship("OzonProduct", back_populates="user")
    wb_punkts = relationship("WbPunkt", back_populates="user")
    wb_products = relationship("WbProduct", back_populates="user")


class WbPunkt(Base):
    __tablename__ = 'wb_punkts'
    
    id = Column(Integer, primary_key=True, index=True)
    lat = Column(Float)
    lon = Column(Float)
    zone = Column(Integer, default=None, nullable=True)
    # expected_price = Column(Float)
    # username = Column(String, nullable=True)
    # first_name = Column(String, nullable=True)
    # last_name = Column(String, nullable=True)
    time_create = Column(TIMESTAMP(timezone=True))
    user_id = Column(Integer, ForeignKey('users.tg_id'))
    
    # Связь с пользователем
    user = relationship(User, back_populates="wb_punkts")
    wb_products = relationship('WbProduct', back_populates="wb_punkt")


class OzonProduct(Base):
    __tablename__ = 'ozon_products'
    
    id = Column(Integer, primary_key=True, index=True)
    link = Column(String)
    short_link = Column(String)
    basic_price = Column(Float)
    actual_price = Column(Float)
    # expected_price = Column(Float)
    # username = Column(String, nullable=True)
    # first_name = Column(String, nullable=True)
    # last_name = Column(String, nullable=True)
    time_create = Column(TIMESTAMP(timezone=True))
    user_id = Column(Integer, ForeignKey('users.tg_id'))
    
    # Связь с пользователем
    user = relationship(User, back_populates="ozon_products")
    wb_punkt = relationship(WbPunkt, back_populates="wb_products")


class WbProduct(Base):
    __tablename__ = 'wb_products'
    
    id = Column(Integer, primary_key=True, index=True)
    link = Column(String)
    short_link = Column(String)
    basic_price = Column(Float)
    actual_price = Column(Float)
    push_price = Column(Float)
    now_price = Column(Float)
    # del_zone = Column(Integer)
    # expected_price = Column(Float)
    # username = Column(String, nullable=True)
    # first_name = Column(String, nullable=True)
    # last_name = Column(String, nullable=True)
    time_create = Column(TIMESTAMP(timezone=True))
    user_id = Column(Integer, ForeignKey('users.tg_id'))
    wb_punkt_id = Column(Integer, ForeignKey('wb_punkts.id'))

    user = relationship(User, back_populates="wb_products")


# Создаем асинхронный движок и сессию
# DATABASE_URL = "sqlite+aiosqlite:///test.db"
engine = create_async_engine(db_url, echo=True)
# AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

# Base = automap_base()

# engine = create_engine(db_url,
#                        echo=True)

# # Base.prepare(engine, reflect=True)
# Base.prepare(autoload_with=engine)

# session = sessionmaker(engine, expire_on_commit=False)