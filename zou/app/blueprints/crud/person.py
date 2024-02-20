from flask import abort
from flask_jwt_extended import jwt_required
from flask_restful import current_app
from sqlalchemy.exc import StatementError

from zou.app.models.person import Person
from zou.app.services import (
    deletion_service,
    index_service,
    persons_service,
)
from zou.app.utils import permissions

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource

from zou.app.mixin import ArgsMixin

from zou.app.services.exception import (
    DepartmentNotFoundException,
    WrongParameterException,
    PersonInProtectedAccounts,
)
from zou.app.models.department import Department

from zou.app import config


class PersonsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Person)

    def all_entries(self, query=None, relations=False):
        if query is None:
            query = self.model.query

        if permissions.has_admin_permissions():
            if self.get_bool_parameter("with_pass_hash"):
                return [
                    person.serialize(relations=relations)
                    for person in query.all()
                ]
            else:
                return [
                    person.serialize_safe(relations=relations)
                    for person in query.all()
                ]
        else:
            return [
                person.present_minimal(relations=relations)
                for person in query.all()
            ]

    def post(self):
        abort(405)

    def check_read_permissions(self):
        return True


class PersonResource(BaseModelResource, ArgsMixin):
    def __init__(self):
        BaseModelResource.__init__(self, Person)
        self.protected_fields += ["password", "jti"]

    def check_read_permissions(self, instance):
        return True

    def check_update_permissions(self, instance_dict, data):
        if instance_dict["id"] != persons_service.get_current_user()["id"]:
            permissions.check_admin_permissions()
        return instance_dict

    def update_data(self, data, instance_id):
        data = super().update_data(data, instance_id)
        if not permissions.has_admin_permissions():
            if not permissions.has_person_permissions():
                data.pop("expiration_date", None)
            data.pop("role", None)
            data.pop("departments", None)
            data.pop("active", None)
            data.pop("is_bot", None)
            data.pop("archived", None)
            data.pop("login_failed_attemps", None)
            data.pop("last_login_failed", None)
            data.pop("is_generated_from_ldap", None)
            data.pop("ldap_uid", None)
            data.pop("last_presence", None)
        return data

    def check_delete_permissions(self, instance_dict):
        if instance_dict["id"] == persons_service.get_current_user()["id"]:
            raise permissions.PermissionDenied
        permissions.check_admin_permissions()
        return instance_dict

    @jwt_required()
    def get(self, instance_id):
        """
        Retrieves the given person.
        """
        relations = self.get_bool_parameter("relations")

        try:
            instance = self.get_model_or_404(instance_id)
            result = self.serialize_instance(instance, relations=relations)
            self.check_read_permissions(result)
            result = self.clean_get_result(result)

        except StatementError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        except ValueError:
            abort(404)

        return result, 200

    def serialize_instance(self, instance, relations=False):
        if permissions.has_manager_permissions():
            return instance.serialize_safe(relations=relations)
        else:
            return instance.present_minimal(relations=relations)

    def pre_update(self, instance_dict, data):
        if (
            not instance_dict.get("active", False)
            and data.get("active", False)
            and not instance_dict.get("is_bot", False)
            and not data.get("is_bot", False)
            and persons_service.is_user_limit_reached()
        ):
            raise WrongParameterException("User limit reached.")
        if (
            data.get("active") is False
            and instance_dict["email"] in config.PROTECTED_ACCOUNTS
        ):
            raise PersonInProtectedAccounts(
                "Can't set this person as inactive it's a protected account."
            )
        return data

    def post_update(self, instance_dict, data):
        persons_service.clear_person_cache()
        index_service.remove_person_index(instance_dict["id"])
        person = persons_service.get_person_raw(instance_dict["id"])
        if person.active:
            index_service.index_person(person)
        instance_dict["departments"] = [
            str(department.id) for department in self.instance.departments
        ]
        if "expiration_date" in data:
            instance_dict["access_token"] = (
                persons_service.create_access_token_for_raw_person(
                    self.instance
                )
            )
        return instance_dict

    def post_delete(self, instance_dict):
        persons_service.clear_person_cache()
        return instance_dict

    def update_data(self, data, instance_id):
        data = super().update_data(data, instance_id)
        if "departments" in data:
            try:
                departments = []
                for department_id in data["departments"]:
                    department = Department.get(department_id)
                    if department is not None:
                        departments.append(department)
            except StatementError:
                raise DepartmentNotFoundException()
            data["departments"] = departments
        return data

    @jwt_required()
    def delete(self, instance_id):
        """
        Delete a person corresponding at given ID and return it as a JSON
        object.
        """
        force = self.get_force()
        person = self.get_model_or_404(instance_id)
        person_dict = person.serialize()
        self.check_delete_permissions(person_dict)
        self.pre_delete(person_dict)
        deletion_service.remove_person(instance_id, force=force)
        index_service.remove_person_index(instance_id)
        self.emit_delete_event(person_dict)
        self.post_delete(person_dict)
        return "", 204
