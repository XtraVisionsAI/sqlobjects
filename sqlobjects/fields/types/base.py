from sqlalchemy.types import TypeEngine

from .comparators import DefaultComparator


class EnhancedType(TypeEngine):
    """Base class for enhanced SQLObjects types with custom comparators"""

    comparator_factory = DefaultComparator

    def __init__(self, **kwargs):
        super().__init__()
        self._enhanced_params = kwargs

    def get_enhanced_params(self):
        """Get enhanced parameters for this type"""
        return self._enhanced_params
