from enum import StrEnum


class UserRole(StrEnum):
    CUSTOMER = "customer"
    MANAGER = "manager"
    ADMIN = "admin"
    CONTENT_MANAGER = "content_manager"
    PICKER = "picker"
    COURIER = "courier"

    def label(self):
        labels = {
            UserRole.CUSTOMER: "Клиент",
            UserRole.MANAGER: "Менеджер",
            UserRole.ADMIN: "Администратор",
            UserRole.CONTENT_MANAGER: "Контент-менеджер",
            UserRole.PICKER: "Сборщик",
            UserRole.COURIER: "Курьер",
        }
        return labels[self]
