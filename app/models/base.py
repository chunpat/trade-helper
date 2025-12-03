from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, DateTime, func
from datetime import datetime

Base = declarative_base()

class TimestampMixin:
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class BaseMixin(TimestampMixin):
    id = Column(Integer, primary_key=True, autoincrement=True)

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
