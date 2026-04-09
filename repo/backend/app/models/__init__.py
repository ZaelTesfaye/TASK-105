"""
Import all models here so that Flask-Migrate / Alembic can discover them
when it introspects the metadata.
"""
from .user import User, Session  # noqa: F401
from .community import Community, ServiceArea, GroupLeaderBinding  # noqa: F401
from .commission import CommissionRule, SettlementRun, SettlementDispute  # noqa: F401
from .catalog import Product, ProductAttribute, ProductTag, SearchLog, TrendingCache  # noqa: F401
from .inventory import (  # noqa: F401
    Warehouse, Bin, InventoryLot, InventoryTransaction,
    CostLayer, AvgCostSnapshot, CycleCount, CycleCountLine,
)
from .messaging import Message, MessageReceipt  # noqa: F401
from .content import (  # noqa: F401
    ContentItem, ContentVersion, Attachment,
    CaptureTemplate, TemplateVersion, TemplateMigration,
)
from .audit import AuditLog, JobLock  # noqa: F401
from .admin import AdminTicket  # noqa: F401
