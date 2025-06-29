from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, BigInteger, String, Numeric, DateTime, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from typing import Optional

class Base(DeclarativeBase):
    pass


class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False)
    type = Column(String(50), nullable=False)  # 'topup', 'payment', 'refund' и т.д.
    amount = Column(Numeric(20, 2), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    admin_id = Column(BigInteger, nullable=True)  # Для операций, выполненных админом

class TransactionRepo:
    def __init__(self, sessionmaker: async_sessionmaker):
        self.sessionmaker = sessionmaker

    async def log(
        self, 
        user_id: int, 
        transaction_type: str, 
        amount: Decimal,
        admin_id: Optional[int] = None
    ) -> None:
        """Логирует транзакцию в базу данных"""
        async with self.sessionmaker() as session:
            async with session.begin():
                transaction = Transaction(
                    user_id=user_id,
                    type=transaction_type,
                    amount=amount,
                    admin_id=admin_id
                )
                session.add(transaction)

    async def get_last_transactions(
        self, 
        user_id: int, 
        limit: int = 5
    ) -> list[dict]:
        """Возвращает последние транзакции пользователя"""
        async with self.sessionmaker() as session:
            result = await session.execute(
                select(Transaction)
                .where(Transaction.user_id == user_id)
                .order_by(Transaction.timestamp.desc())
                .limit(limit)
            )
            transactions = result.scalars().all()
            
            return [
                {
                    "id": t.id,
                    "type": t.type,
                    "amount": float(t.amount),
                    "timestamp": t.timestamp.isoformat(),
                    "admin_id": t.admin_id
                }
                for t in transactions
            ]