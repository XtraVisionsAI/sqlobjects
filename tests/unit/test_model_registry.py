"""Explicit registries keep application schemas isolated for migrations."""

from typing import Any, cast

import pytest
from sqlalchemy import MetaData

from sqlobjects.fields import Column, StringColumn, foreign_key, identity
from sqlobjects.metadata import ModelRegistry
from sqlobjects.model import ObjectModel


def test_explicit_registry_is_inherited_without_polluting_shared_metadata():
    registry = ModelRegistry(naming_convention={"pk": "pk_%(table_name)s", "fk": "fk_%(table_name)s_%(column_0_name)s"})
    shared_tables = set(ObjectModel.__registry__.tables)

    class AppBase(ObjectModel):
        __abstract__ = True
        __registry__ = registry

    assert AppBase.__registry__ is registry

    class Parent(AppBase):
        id: Column[int] = identity()

        class Config:
            table_name = "isolated_parents"

    class Child(AppBase):
        id: Column[int] = identity()
        parent_id: Column[int] = foreign_key("isolated_parents.id")

        class Config:
            table_name = "isolated_children"

    assert Parent.__table__.metadata is registry
    assert Child.__table__.metadata is registry
    assert registry.get_model("Parent") is Parent
    assert next(iter(Child.__table__.c.parent_id.foreign_keys)).column is Parent.__table__.c.id
    assert Parent.__table__.primary_key.name == "pk_isolated_parents"
    assert set(ObjectModel.__registry__.tables) == shared_tables


def test_two_registries_can_define_the_same_table_independently():
    first, second = ModelRegistry(), ModelRegistry()

    class FirstBase(ObjectModel):
        __abstract__ = True
        __registry__ = first

    class SecondBase(ObjectModel):
        __abstract__ = True
        __registry__ = second

    assert FirstBase.__registry__ is not SecondBase.__registry__

    class First(FirstBase):
        id: Column[int] = identity()
        name: Column[str] = StringColumn(length=30)

        class Config:
            table_name = "same_table"

    class Second(SecondBase):
        id: Column[int] = identity()

        class Config:
            table_name = "same_table"

    assert set(first.tables["same_table"].c.keys()) == {"id", "name"}
    assert set(second.tables["same_table"].c.keys()) == {"id"}


@pytest.mark.parametrize("registry", [None, MetaData(), object()])
def test_invalid_explicit_registry_is_rejected(registry):
    with pytest.raises(TypeError, match="ModelRegistry"):

        class InvalidBase(ObjectModel):
            __abstract__ = True
            __registry__ = cast(Any, registry)


def test_default_registry_remains_shared():
    class SharedBase(ObjectModel):
        __abstract__ = True

    assert SharedBase.__registry__ is ObjectModel.__registry__
