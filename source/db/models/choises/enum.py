from enum import StrEnum


class UserRole(StrEnum):
    CUSTOMER = "customer"
    MANAGER = "manager"
    ADMIN = "admin"

    def label(self):
        labels = {
            UserRole.CUSTOMER: "Клиент",
            UserRole.MANAGER: "Менеджер",
            UserRole.ADMIN: "Администратор",
        }
        return labels[self]
