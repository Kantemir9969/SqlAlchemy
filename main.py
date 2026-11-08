from datetime import date, timedelta
from sqlalchemy import (
    create_engine, Column, Integer, String, Date, DateTime, Numeric, Text,
    ForeignKey, func
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

engine = create_engine("sqlite:///rental.db", echo=False, future=True)
Session = sessionmaker(bind=engine, future=True)
session = Session()

Base = declarative_base()


EQUIP_STATUS_AVAILABLE = "AVAILABLE"
EQUIP_STATUS_RENTED = "RENTED"
EQUIP_STATUS_IN_SERVICE = "IN_SERVICE"

CONTRACT_STATUS_ACTIVE = "ACTIVE"
CONTRACT_STATUS_CLOSED = "CLOSED"
CONTRACT_STATUS_CANCELLED = "CANCELLED"

ITEM_STATUS_ISSUED = "ISSUED"
ITEM_STATUS_RETURNED = "RETURNED"
ITEM_STATUS_LATE = "LATE"


class Type(Base):
    __tablename__ = "equipment_type"

    type_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True)
    models = relationship("Model", back_populates="type")

class Model(Base):
    __tablename__ = "equipment_model"

    model_id = Column(Integer, primary_key=True, autoincrement=True)
    type_id = Column(Integer, ForeignKey("equipment_type.type_id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    daily_rate = Column(Numeric(12, 2), nullable=False, default=0)
    type = relationship("Type", back_populates="models")
    instances = relationship("Instance", back_populates="model")

class Instance(Base):
    __tablename__ = "equipment_instance"

    instance_id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(Integer, ForeignKey("equipment_model.model_id"), nullable=False)
    inventory_number = Column(String(50), nullable=False, unique=True)
    status = Column(String(20), nullable=False)  # без Enum
    current_condition = Column(String(100))
    location = Column(String(50))
    acquired_date = Column(Date)
    model = relationship("Model", back_populates="instances")
    contract_items = relationship("RentalContractItem", back_populates="instance")

class Customer(Base):
    __tablename__ = "customer"

    customer_id = Column(Integer, primary_key=True, autoincrement=True)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    phone = Column(String(20))
    email = Column(String(100))
    address = Column(Text)
    contracts = relationship("RentalContract", back_populates="customer")

class Employee(Base):
    __tablename__ = "employee"

    employee_id = Column(Integer, primary_key=True, autoincrement=True)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    role = Column(String(50))
    phone = Column(String(20))
    email = Column(String(100))
    status_history = relationship("RentalStatusHistory", back_populates="changed_by")

class RentalContract(Base):
    __tablename__ = "rental_contract"

    contract_id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customer.customer_id"), nullable=False)
    contract_date = Column(Date, nullable=False)
    agreed_total_cost = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(8), nullable=False, default="RUB")
    status = Column(String(20), nullable=False, default=CONTRACT_STATUS_ACTIVE)
    customer = relationship("Customer", back_populates="contracts")
    items = relationship("RentalContractItem", back_populates="contract")
    payments = relationship("Payment", back_populates="contract")

class RentalContractItem(Base):
    __tablename__ = "rental_contract_item"

    contract_item_id = Column(Integer, primary_key=True, autoincrement=True)
    contract_id = Column(Integer, ForeignKey("rental_contract.contract_id"), nullable=False)
    instance_id = Column(Integer, ForeignKey("equipment_instance.instance_id"), nullable=False)
    planned_return_date = Column(Date, nullable=False)
    actual_return_date = Column(Date)
    price_at_rent = Column(Numeric(12, 2), nullable=False)
    issued_by_employee_id = Column(Integer, ForeignKey("employee.employee_id"), nullable=False)
    status = Column(String(20), nullable=False, default=ITEM_STATUS_ISSUED)
    contract = relationship("RentalContract", back_populates="items")
    instance = relationship("Instance", back_populates="contract_items")

class Payment(Base):
    __tablename__ = "payment"

    payment_id = Column(Integer, primary_key=True, autoincrement=True)
    contract_id = Column(Integer, ForeignKey("rental_contract.contract_id"), nullable=False)
    payment_date = Column(Date, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    method = Column(String(50))
    contract = relationship("RentalContract", back_populates="payments")

class RentalStatusHistory(Base):
    __tablename__ = "rental_status_history"

    history_id = Column(Integer, primary_key=True, autoincrement=True)
    contract_item_id = Column(Integer, ForeignKey("rental_contract_item.contract_item_id"), nullable=False)
    changed_by_employee_id = Column(Integer, ForeignKey("employee.employee_id"), nullable=False)
    old_status = Column(String(20), nullable=False)
    new_status = Column(String(20), nullable=False)
    changed_at = Column(DateTime, nullable=False, default=func.now())
    contract_item = relationship("RentalContractItem")
    changed_by = relationship("Employee", back_populates="status_history")


Base.metadata.create_all(engine)

def query_available_by_type(session, type_name="Велосипед"):
    return session.query(Instance).join(Instance.model).join(Model.type).filter(
        Type.name == type_name,
        Instance.status == EQUIP_STATUS_AVAILABLE
    ).all()

def query_overdue_returns(session):
    today = date.today()
    results = session.query(
        RentalContract.contract_id,
        Customer.customer_id,
        (Customer.first_name + " " + Customer.last_name).label("customer_name"),
        Customer.phone,
        Customer.email,
        Instance.inventory_number,
        Model.name.label("model_name"),
        Type.name.label("type_name"),
        RentalContractItem.planned_return_date
    ).join(RentalContract.items).join(RentalContract.customer).join(RentalContractItem.instance).join(Instance.model).join(Model.type).filter(
        RentalContractItem.actual_return_date == None,
        RentalContractItem.planned_return_date < today
    ).all()
    return results

def query_costs_and_payments(session):
    sub_cost = session.query(
        RentalContract.contract_id.label("contract_id"),
        func.sum(RentalContractItem.price_at_rent).label("total_cost")
    ).join(RentalContract.items).group_by(RentalContract.contract_id).subquery()

    sub_pay = session.query(
        Payment.contract_id.label("contract_id"),
        func.sum(Payment.amount).label("payments")
    ).group_by(Payment.contract_id).subquery()

    results = session.query(
        RentalContract.contract_id,
        sub_cost.c.total_cost,
        func.coalesce(sub_pay.c.payments, 0).label("payments"),
        (sub_cost.c.total_cost - func.coalesce(sub_pay.c.payments, 0)).label("remaining")
    ).outerjoin(sub_cost, RentalContract.contract_id == sub_cost.c.contract_id
    ).outerjoin(sub_pay, RentalContract.contract_id == sub_pay.c.contract_id
    ).order_by(RentalContract.contract_id).all()

    return results

def query_top_types_by_month(session):
    today = date.today()
    first_day = today.replace(day=1)

    if today.month == 12:
        next_month = today.replace(year=today.year + 1, month=1, day=1)
    else:
        next_month = today.replace(month=today.month + 1, day=1)

    return (
        session.query(
            Type.name.label("type_name"),
            func.count(RentalContractItem.contract_item_id).label("rented_count")
        )
        .select_from(RentalContractItem)
        .join(RentalContractItem.contract)
        .join(RentalContractItem.instance)
        .join(Instance.model)
        .join(Model.type)
        .filter(
            RentalContract.contract_date >= first_day,
            RentalContract.contract_date < next_month
        )
        .group_by(Type.name)
        .all()
    )


bike = Type(name="Велосипед")
scooter = Type(name="Самокат")
skis = Type(name="Лыжи")
session.add_all([bike, scooter, skis])
session.flush()

mtb = Model(type_id=bike.type_id, name='MTB 29"', description='Горный велосипед 29"', daily_rate=15)
city_scooter = Model(type_id=scooter.type_id, name='City Scooter 300', description='Электросамокат', daily_rate=20)
skis_model = Model(type_id=skis.type_id, name='All-Mnow X200', description='Лыжи для трассы', daily_rate=12.5)
session.add_all([mtb, city_scooter, skis_model])
session.flush()

eb1 = Instance(model_id=mtb.model_id, inventory_number='B-001', status=EQUIP_STATUS_AVAILABLE, current_condition='Хорошее', location='Склад', acquired_date=date(2024,3,1))
eb2 = Instance(model_id=mtb.model_id, inventory_number='B-002', status=EQUIP_STATUS_AVAILABLE, current_condition='Хорошее', location='Склад', acquired_date=date(2024,3,5))
es1 = Instance(model_id=city_scooter.model_id, inventory_number='S-101', status=EQUIP_STATUS_AVAILABLE, current_condition='Отличное', location='Склад', acquired_date=date(2025,5,10))
el1 = Instance(model_id=skis_model.model_id, inventory_number='L-701', status=EQUIP_STATUS_IN_SERVICE, current_condition='Подготовка', location='Сервис', acquired_date=date(2025,1,15))
session.add_all([eb1, eb2, es1, el1])

c1 = Customer(first_name='Иван', last_name='Иванов', phone='+79260000001', email='ivan@example.com', address='Москва, ул. Примерная, д.1')
c2 = Customer(first_name='Мария', last_name='Петрова', phone='+79260000002', email='maria@example.com', address='Москва, пр. Мира, д.2')
session.add_all([c1, c2])

e1 = Employee(first_name='Олег', last_name='Смирнов', role='администратор', phone='+79260000010', email='oleg@example.com')
e2 = Employee(first_name='Елена', last_name='Кузнецова', role='оператор', phone='+79260000011', email='elena@example.com')
session.add_all([e1, e2])
session.flush()

d0 = date.today()
cton1 = RentalContract(customer_id=c1.customer_id, contract_date=d0 - timedelta(days=5), agreed_total_cost=45.00, currency='RUB', status=CONTRACT_STATUS_ACTIVE)
cton2 = RentalContract(customer_id=c2.customer_id, contract_date=d0 - timedelta(days=2), agreed_total_cost=30.00, currency='RUB', status=CONTRACT_STATUS_ACTIVE)
session.add_all([cton1, cton2])
session.flush()

rci1 = RentalContractItem(contract_id=cton1.contract_id, instance_id=eb1.instance_id,
                                  planned_return_date=d0 + timedelta(days=2), actual_return_date=None,
                                  price_at_rent=15.00, issued_by_employee_id=e1.employee_id, status=ITEM_STATUS_ISSUED)
rci2 = RentalContractItem(contract_id=cton1.contract_id, instance_id=es1.instance_id,
                                  planned_return_date=d0 + timedelta(days=1), actual_return_date=None,
                                  price_at_rent=20.00, issued_by_employee_id=e1.employee_id, status=ITEM_STATUS_ISSUED)
rci3 = RentalContractItem(contract_id=cton2.contract_id, instance_id=eb2.instance_id,
                                  planned_return_date=d0 + timedelta(days=3), actual_return_date=None,
                                  price_at_rent=15.00, issued_by_employee_id=e2.employee_id, status=ITEM_STATUS_ISSUED)
session.add_all([rci1, rci2, rci3])
session.flush()

p1 = Payment(contract_id=cton1.contract_id, payment_date=d0 - timedelta(days=4), amount=15.00, method='cash')
p2 = Payment(contract_id=cton2.contract_id, payment_date=d0 - timedelta(days=1), amount=10.00, method='cash')
session.add_all([p1, p2])


available_bikes = query_available_by_type(session, "Велосипед")
for item in available_bikes:
    print(f"inv='{item.inventory_number}', model='{item.model.name}', type='{item.model.type.name}', status = '{item.status}'")

overdue = query_overdue_returns(session)
for r in overdue:
    print(
        f"Contract {r.contract_id}, Customer {r.customer_name}, "
        f"Phone {r.phone}, Email {r.email}, "
        f"Item {r.inventory_number} ({r.model_name} / {r.type_name}), "
        f"PlannedReturn {r.planned_return_date}"
    )

costs = query_costs_and_payments(session)
for c in costs:
    print(f"Contract {c.contract_id}: total_cost = {c.total_cost}, payments = {c.payments}, remaining = {c.remaining}")

top = query_top_types_by_month(session)
for r in top:
    print(f"Type {r.type_name}, rented_count = {r.rented_count}")


