# Relationships

> 📝 This document is based on the Chinese version. For the latest Chinese version, see [docs-zh/design/04-relationships.md](../../docs-zh/design/04-relationships.md)

This document describes the internal architecture and implementation details of SQLObjects' relationship system, including relationship loading strategies, proxy objects, and performance optimizations.

## Relationship Architecture

### Core Components

```python
# Relationship system structure
fields/relations/
├── __init__.py      # Public relationship API
├── descriptors.py   # Relationship descriptors and access
├── managers.py      # Relationship managers and queries
├── proxies.py       # Lazy loading proxy objects
└── utils.py         # Relationship utilities
```

### Relationship Types

```python
from enum import Enum

class RelationshipType(Enum):
    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    MANY_TO_MANY = "many_to_many"

class RelationshipDefinition:
    """Define relationship between models"""
    
    def __init__(
        self,
        related_model: str,
        relationship_type: RelationshipType,
        foreign_key: str = None,
        back_populates: str = None,
        secondary: str = None,
        lazy: str = "select",
        cascade: str = None,
        order_by: str = None,
        primaryjoin: str = None,
        **kwargs
    ):
        self.related_model = related_model
        self.relationship_type = relationship_type
        self.foreign_key = foreign_key
        self.back_populates = back_populates
        self.secondary = secondary  # For many-to-many
        self.lazy = lazy
        self.cascade = cascade
        self.order_by = order_by
        self.primaryjoin = primaryjoin
        self.kwargs = kwargs
    
    def __set_name__(self, owner, name):
        """Called when relationship is assigned to model class"""
        self.name = name
        self.owner_model = owner
```

### Relationship Descriptor

```python
class RelationshipDescriptor:
    """Descriptor for relationship field access"""
    
    def __init__(self, relationship_def: RelationshipDefinition):
        self.relationship_def = relationship_def
        self.name = None
    
    def __set_name__(self, owner, name):
        self.name = name
        self.relationship_def.__set_name__(owner, name)
    
    def __get__(self, instance, owner):
        """Get relationship value from instance"""
        if instance is None:
            return self
        
        # Check if relationship is already loaded
        cache_attr = f"_{self.name}_cache"
        if hasattr(instance, cache_attr):
            return getattr(instance, cache_attr)
        
        # Create relationship manager
        manager = self._create_manager(instance)
        setattr(instance, cache_attr, manager)
        return manager
    
    def __set__(self, instance, value):
        """Set relationship value on instance"""
        cache_attr = f"_{self.name}_cache"
        
        if self.relationship_def.relationship_type in [RelationshipType.ONE_TO_ONE, RelationshipType.MANY_TO_ONE]:
            # Direct assignment for single-valued relationships
            setattr(instance, cache_attr, value)
        else:
            # For collections, replace the manager
            manager = self._create_manager(instance)
            if hasattr(value, '__iter__'):
                manager.set(value)
            setattr(instance, cache_attr, manager)
    
    def _create_manager(self, instance):
        """Create appropriate relationship manager"""
        if self.relationship_def.relationship_type in [RelationshipType.ONE_TO_ONE, RelationshipType.MANY_TO_ONE]:
            return SingleRelationshipManager(instance, self.relationship_def)
        else:
            return CollectionRelationshipManager(instance, self.relationship_def)
```

### Relationship Managers

```python
class BaseRelationshipManager:
    """Base class for relationship managers"""
    
    def __init__(self, instance, relationship_def: RelationshipDefinition):
        self.instance = instance
        self.relationship_def = relationship_def
        self._loaded = False
        self._cached_value = None
    
    def _get_related_model(self):
        """Get related model class"""
        # Import related model (handle circular imports)
        from sqlobjects.model import ObjectModel
        
        # Find model in registry
        for model_class in ObjectModel.__subclasses__():
            if model_class.__name__ == self.relationship_def.related_model:
                return model_class
        
        raise ValueError(f"Related model not found: {self.relationship_def.related_model}")
    
    def _get_session(self):
        """Get database session from instance"""
        return getattr(self.instance, '_session', None)

class SingleRelationshipManager(BaseRelationshipManager):
    """Manager for one-to-one and many-to-one relationships"""
    
    async def get(self):
        """Get related object"""
        if self._loaded:
            return self._cached_value
        
        related_model = self._get_related_model()
        session = self._get_session()
        
        # Get foreign key value
        fk_field = self.relationship_def.foreign_key
        if not fk_field:
            fk_field = f"{self.relationship_def.related_model.lower()}_id"
        
        fk_value = getattr(self.instance, fk_field)
        if fk_value is None:
            self._cached_value = None
            self._loaded = True
            return None
        
        # Query related object
        if session:
            related_obj = await related_model.objects.using(session).get(
                getattr(related_model, "id") == fk_value
            )
        else:
            related_obj = await related_model.objects.get(
                getattr(related_model, "id") == fk_value
            )
        
        self._cached_value = related_obj
        self._loaded = True
        return related_obj
    
    async def set(self, value):
        """Set related object"""
        if value is None:
            # Clear relationship
            fk_field = self.relationship_def.foreign_key or f"{self.relationship_def.related_model.lower()}_id"
            setattr(self.instance, fk_field, None)
        else:
            # Set foreign key
            fk_field = self.relationship_def.foreign_key or f"{self.relationship_def.related_model.lower()}_id"
            setattr(self.instance, fk_field, value.id)
        
        self._cached_value = value
        self._loaded = True
    
    def __await__(self):
        """Make manager awaitable"""
        return self.get().__await__()

class CollectionRelationshipManager(BaseRelationshipManager):
    """Manager for one-to-many and many-to-many relationships"""
    
    def __init__(self, instance, relationship_def: RelationshipDefinition):
        super().__init__(instance, relationship_def)
        self._added_items = set()
        self._removed_items = set()
    
    async def all(self):
        """Get all related objects"""
        if self._loaded:
            return list(self._cached_value)
        
        related_model = self._get_related_model()
        session = self._get_session()
        
        if self.relationship_def.relationship_type == RelationshipType.ONE_TO_MANY:
            # Query by foreign key
            fk_field = self._get_reverse_foreign_key()
            query = related_model.objects.filter(
                getattr(related_model, fk_field) == self.instance.id
            )
        else:
            # Many-to-many through secondary table
            query = self._build_many_to_many_query(related_model)
        
        if session:
            query = query.using(session)
        
        # Apply ordering if specified
        if self.relationship_def.order_by:
            query = query.order_by(self.relationship_def.order_by)
        
        related_objects = await query.all()
        
        self._cached_value = related_objects
        self._loaded = True
        return related_objects
    
    async def filter(self, *conditions, **kwargs):
        """Filter related objects"""
        related_model = self._get_related_model()
        session = self._get_session()
        
        if self.relationship_def.relationship_type == RelationshipType.ONE_TO_MANY:
            # Add foreign key condition
            fk_field = self._get_reverse_foreign_key()
            base_condition = getattr(related_model, fk_field) == self.instance.id
            
            if conditions:
                from sqlalchemy import and_
                query = related_model.objects.filter(and_(base_condition, *conditions))
            else:
                query = related_model.objects.filter(base_condition)
        else:
            # Many-to-many filtering
            query = self._build_many_to_many_query(related_model)
            if conditions:
                query = query.filter(*conditions)
        
        if kwargs:
            query = query.filter(**kwargs)
        
        if session:
            query = query.using(session)
        
        return await query.all()
    
    async def count(self):
        """Count related objects"""
        related_model = self._get_related_model()
        session = self._get_session()
        
        if self.relationship_def.relationship_type == RelationshipType.ONE_TO_MANY:
            fk_field = self._get_reverse_foreign_key()
            query = related_model.objects.filter(
                getattr(related_model, fk_field) == self.instance.id
            )
        else:
            query = self._build_many_to_many_query(related_model)
        
        if session:
            query = query.using(session)
        
        return await query.count()
    
    async def exists(self):
        """Check if any related objects exist"""
        return await self.count() > 0
    
    async def add(self, *objects):
        """Add objects to relationship"""
        if self.relationship_def.relationship_type == RelationshipType.ONE_TO_MANY:
            # Set foreign key on related objects
            fk_field = self._get_reverse_foreign_key()
            for obj in objects:
                setattr(obj, fk_field, self.instance.id)
                await obj.save()
        else:
            # Many-to-many: create association records
            await self._create_associations(objects)
        
        # Update cache
        if self._loaded:
            self._cached_value.extend(objects)
        
        self._added_items.update(objects)
    
    async def remove(self, *objects):
        """Remove objects from relationship"""
        if self.relationship_def.relationship_type == RelationshipType.ONE_TO_MANY:
            # Clear foreign key on related objects
            fk_field = self._get_reverse_foreign_key()
            for obj in objects:
                setattr(obj, fk_field, None)
                await obj.save()
        else:
            # Many-to-many: delete association records
            await self._delete_associations(objects)
        
        # Update cache
        if self._loaded:
            for obj in objects:
                if obj in self._cached_value:
                    self._cached_value.remove(obj)
        
        self._removed_items.update(objects)
    
    async def clear(self):
        """Remove all objects from relationship"""
        if self._loaded:
            objects = list(self._cached_value)
        else:
            objects = await self.all()
        
        await self.remove(*objects)
    
    async def set(self, objects):
        """Replace all objects in relationship"""
        await self.clear()
        await self.add(*objects)
    
    def _get_reverse_foreign_key(self):
        """Get foreign key field name for reverse relationship"""
        return f"{self.instance.__class__.__name__.lower()}_id"
    
    def _build_many_to_many_query(self, related_model):
        """Build query for many-to-many relationship"""
        # This would involve joining through the secondary table
        # Implementation depends on the specific secondary table structure
        pass
    
    async def _create_associations(self, objects):
        """Create many-to-many association records"""
        # Implementation for creating association table records
        pass
    
    async def _delete_associations(self, objects):
        """Delete many-to-many association records"""
        # Implementation for deleting association table records
        pass
```

### Relationship Loading Strategies

```python
class RelationshipLoader:
    """Handle different relationship loading strategies"""
    
    def __init__(self, session):
        self.session = session
    
    async def load_select_related(self, objects, related_fields):
        """Load relationships using JOINs (select_related)"""
        if not objects or not related_fields:
            return objects
        
        model_class = objects[0].__class__
        
        # Build query with JOINs
        query = self._build_join_query(model_class, related_fields)
        
        # Execute query
        result = await self.session.execute(query)
        rows = result.fetchall()
        
        # Process results and populate relationships
        self._populate_joined_relationships(objects, rows, related_fields)
        
        return objects
    
    async def load_prefetch_related(self, objects, related_fields):
        """Load relationships using separate queries (prefetch_related)"""
        if not objects or not related_fields:
            return objects
        
        for field_name in related_fields:
            await self._prefetch_field(objects, field_name)
        
        return objects
    
    def _build_join_query(self, model_class, related_fields):
        """Build query with JOINs for select_related"""
        from sqlalchemy import select
        
        # Start with main table
        tables = [model_class.__table__]
        join_conditions = []
        
        for field_name in related_fields:
            # Get relationship definition
            relationship_def = getattr(model_class, field_name).relationship_def
            related_model = self._get_related_model(relationship_def.related_model)
            
            # Add JOIN
            if relationship_def.relationship_type in [RelationshipType.MANY_TO_ONE, RelationshipType.ONE_TO_ONE]:
                # JOIN on foreign key
                fk_field = relationship_def.foreign_key or f"{relationship_def.related_model.lower()}_id"
                join_condition = getattr(model_class.__table__.c, fk_field) == related_model.__table__.c.id
                join_conditions.append((related_model.__table__, join_condition))
        
        # Build SELECT with JOINs
        query = select(*[table for table in tables])
        for join_table, condition in join_conditions:
            query = query.join(join_table, condition)
        
        return query
    
    async def _prefetch_field(self, objects, field_name):
        """Prefetch single relationship field"""
        if not objects:
            return
        
        model_class = objects[0].__class__
        relationship_def = getattr(model_class, field_name).relationship_def
        related_model = self._get_related_model(relationship_def.related_model)
        
        if relationship_def.relationship_type == RelationshipType.ONE_TO_MANY:
            await self._prefetch_one_to_many(objects, field_name, related_model, relationship_def)
        elif relationship_def.relationship_type == RelationshipType.MANY_TO_MANY:
            await self._prefetch_many_to_many(objects, field_name, related_model, relationship_def)
    
    async def _prefetch_one_to_many(self, objects, field_name, related_model, relationship_def):
        """Prefetch one-to-many relationship"""
        # Get primary keys of main objects
        object_ids = [obj.id for obj in objects]
        
        # Query related objects
        fk_field = f"{objects[0].__class__.__name__.lower()}_id"
        related_objects = await related_model.objects.filter(
            getattr(related_model, fk_field).in_(object_ids)
        ).all()
        
        # Group related objects by foreign key
        related_by_id = {}
        for related_obj in related_objects:
            fk_value = getattr(related_obj, fk_field)
            if fk_value not in related_by_id:
                related_by_id[fk_value] = []
            related_by_id[fk_value].append(related_obj)
        
        # Attach to main objects
        for obj in objects:
            related_list = related_by_id.get(obj.id, [])
            
            # Create and populate relationship manager
            manager = CollectionRelationshipManager(obj, relationship_def)
            manager._cached_value = related_list
            manager._loaded = True
            
            setattr(obj, f"_relationship_{field_name}", manager)
    
    async def _prefetch_many_to_many(self, objects, field_name, related_model, relationship_def):
        """Prefetch many-to-many relationship"""
        # Implementation for many-to-many prefetching
        # This involves querying through the association table
        pass
    
    def _get_related_model(self, model_name):
        """Get related model class by name"""
        from sqlobjects.model import ObjectModel
        
        for model_class in ObjectModel.__subclasses__():
            if model_class.__name__ == model_name:
                return model_class
        
        raise ValueError(f"Related model not found: {model_name}")
```

### Relationship Proxy Objects

```python
class RelationshipProxy:
    """Proxy object for lazy relationship loading"""
    
    def __init__(self, instance, relationship_def: RelationshipDefinition):
        self.instance = instance
        self.relationship_def = relationship_def
        self._manager = None
    
    def _get_manager(self):
        """Get or create relationship manager"""
        if self._manager is None:
            if self.relationship_def.relationship_type in [RelationshipType.ONE_TO_ONE, RelationshipType.MANY_TO_ONE]:
                self._manager = SingleRelationshipManager(self.instance, self.relationship_def)
            else:
                self._manager = CollectionRelationshipManager(self.instance, self.relationship_def)
        return self._manager
    
    def __getattr__(self, name):
        """Delegate attribute access to relationship manager"""
        manager = self._get_manager()
        return getattr(manager, name)
    
    def __await__(self):
        """Make proxy awaitable for single relationships"""
        if self.relationship_def.relationship_type in [RelationshipType.ONE_TO_ONE, RelationshipType.MANY_TO_ONE]:
            manager = self._get_manager()
            return manager.get().__await__()
        else:
            raise TypeError("Collection relationships are not awaitable, use .all() instead")

class DeferredRelationshipProxy:
    """Proxy for deferred relationship loading with error handling"""
    
    def __init__(self, instance, field_name):
        self.instance = instance
        self.field_name = field_name
    
    async def fetch(self):
        """Fetch the deferred relationship"""
        # Load the relationship from database
        relationship_def = getattr(self.instance.__class__, self.field_name).relationship_def
        
        if relationship_def.relationship_type in [RelationshipType.ONE_TO_ONE, RelationshipType.MANY_TO_ONE]:
            manager = SingleRelationshipManager(self.instance, relationship_def)
            return await manager.get()
        else:
            manager = CollectionRelationshipManager(self.instance, relationship_def)
            return await manager.all()
    
    def __getattr__(self, name):
        """Provide helpful error messages for deferred relationships"""
        raise AttributeError(
            f"Relationship '{self.field_name}' is deferred and not loaded. "
            f"Use 'await obj.{self.field_name}.fetch()' to load it, or use "
            f"select_related('{self.field_name}') or prefetch_related('{self.field_name}') "
            f"in your query to load it automatically."
        )
    
    def __len__(self):
        raise TypeError(
            f"Cannot get length of deferred relationship '{self.field_name}'. "
            f"Use 'await obj.{self.field_name}.fetch()' first."
        )
    
    def __bool__(self):
        raise TypeError(
            f"Cannot evaluate truth value of deferred relationship '{self.field_name}'. "
            f"Use 'await obj.{self.field_name}.fetch()' first."
        )
```

### Relationship Performance Optimization

```python
class RelationshipOptimizer:
    """Optimize relationship loading performance"""
    
    @staticmethod
    def analyze_relationship_queries(model_class, query_pattern):
        """Analyze relationship access patterns and suggest optimizations"""
        suggestions = []
        
        # Detect N+1 query patterns
        if "select" in query_pattern and "relationship_access" in query_pattern:
            suggestions.append({
                "type": "n_plus_one",
                "message": "Potential N+1 query detected",
                "solution": "Use select_related() or prefetch_related()"
            })
        
        # Detect unused relationship loading
        if "select_related" in query_pattern and "relationship_unused" in query_pattern:
            suggestions.append({
                "type": "unused_loading",
                "message": "Loading relationships that are not used",
                "solution": "Remove unused select_related() or prefetch_related()"
            })
        
        return suggestions
    
    @staticmethod
    def optimize_relationship_loading(objects, access_pattern):
        """Optimize relationship loading based on access patterns"""
        # Analyze which relationships are actually accessed
        accessed_relationships = set()
        
        for obj in objects:
            for attr_name in dir(obj):
                if attr_name.startswith('_relationship_'):
                    rel_name = attr_name[13:]  # Remove '_relationship_' prefix
                    if rel_name in access_pattern:
                        accessed_relationships.add(rel_name)
        
        return list(accessed_relationships)
    
    @staticmethod
    def batch_relationship_loading(objects, relationship_name, batch_size=100):
        """Load relationships in batches for memory efficiency"""
        async def load_batch(batch):
            # Load relationships for batch of objects
            loader = RelationshipLoader(None)  # Session would be provided
            await loader.load_prefetch_related(batch, [relationship_name])
        
        # Process objects in batches
        for i in range(0, len(objects), batch_size):
            batch = objects[i:i + batch_size]
            yield load_batch(batch)
```

### Relationship Validation

```python
class RelationshipValidator:
    """Validate relationship definitions and constraints"""
    
    @staticmethod
    def validate_relationship_definition(relationship_def: RelationshipDefinition):
        """Validate relationship definition"""
        errors = []
        
        # Check required fields
        if not relationship_def.related_model:
            errors.append("Related model is required")
        
        # Validate many-to-many relationships
        if relationship_def.relationship_type == RelationshipType.MANY_TO_MANY:
            if not relationship_def.secondary:
                errors.append("Many-to-many relationships require secondary table")
        
        # Validate foreign key relationships
        if relationship_def.relationship_type in [RelationshipType.MANY_TO_ONE, RelationshipType.ONE_TO_ONE]:
            if not relationship_def.foreign_key:
                # Auto-generate foreign key name
                relationship_def.foreign_key = f"{relationship_def.related_model.lower()}_id"
        
        if errors:
            raise ValueError(f"Invalid relationship definition: {', '.join(errors)}")
    
    @staticmethod
    def validate_relationship_integrity(instance, relationship_name, value):
        """Validate relationship integrity constraints"""
        relationship_def = getattr(instance.__class__, relationship_name).relationship_def
        
        # Validate foreign key constraints
        if relationship_def.relationship_type in [RelationshipType.MANY_TO_ONE, RelationshipType.ONE_TO_ONE]:
            if value is not None:
                # Check that related object exists and is of correct type
                related_model = RelationshipValidator._get_related_model(relationship_def.related_model)
                if not isinstance(value, related_model):
                    raise ValueError(f"Expected {related_model.__name__}, got {type(value).__name__}")
        
        # Validate collection constraints
        elif relationship_def.relationship_type in [RelationshipType.ONE_TO_MANY, RelationshipType.MANY_TO_MANY]:
            if value is not None and hasattr(value, '__iter__'):
                related_model = RelationshipValidator._get_related_model(relationship_def.related_model)
                for item in value:
                    if not isinstance(item, related_model):
                        raise ValueError(f"All items must be {related_model.__name__} instances")
    
    @staticmethod
    def _get_related_model(model_name):
        """Get related model class by name"""
        from sqlobjects.model import ObjectModel
        
        for model_class in ObjectModel.__subclasses__():
            if model_class.__name__ == model_name:
                return model_class
        
        raise ValueError(f"Related model not found: {model_name}")
```

This relationship architecture provides the foundation for SQLObjects' powerful and efficient relationship system with lazy loading, performance optimization, and comprehensive validation capabilities.