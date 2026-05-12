from enum import StrEnum


class UserRole(StrEnum):
    CUSTOMER = "customer"

    def label(self):
        labels = {
            UserRole.CUSTOMER: "Клиент",
        }
        return labels[self]
