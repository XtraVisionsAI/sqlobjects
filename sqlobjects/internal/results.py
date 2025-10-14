"""Internal result processing utilities

This module provides result processing utilities shared by Model
and Bulk operations. These are internal utilities and should not
be used directly by end users.
"""

__all__ = ["ResultProcessor"]


class ResultProcessor:
    """Result processing utilities for internal use

    Provides utilities for converting database rows to dictionaries
    or model instances, used by both Model and Bulk operations.
    """

    @staticmethod
    def rows_to_dicts(rows):
        """Convert database rows to dictionaries

        Args:
            rows: Database result rows with _mapping attribute

        Returns:
            List of dictionaries
        """
        return [dict(row._mapping) for row in rows]

    @staticmethod
    def rows_to_objects(rows, model_class, return_fields=None):
        """Convert database rows to model instances or filtered dicts

        Args:
            rows: Database result rows with _mapping attribute
            model_class: Model class to instantiate
            return_fields: Optional list of fields to return
                         If specified, returns dicts instead of instances

        Returns:
            List of model instances (if return_fields is None)
            or list of dictionaries (if return_fields is specified)
        """
        objects = []
        for row in rows:
            row_dict = dict(row._mapping)

            if return_fields:
                # Return filtered dictionary with only requested fields
                filtered_dict = {f: row_dict.get(f) for f in return_fields}
                objects.append(filtered_dict)
            else:
                # Return full model instance
                obj = model_class.from_dict(row_dict, validate=False)
                objects.append(obj)

        return objects

    @staticmethod
    def extract_field_values(instances, field_name):
        """Extract field values from model instances

        Args:
            instances: List of model instances
            field_name: Field name to extract

        Returns:
            List of field values (may contain None)
        """
        return [getattr(inst, field_name, None) for inst in instances]
