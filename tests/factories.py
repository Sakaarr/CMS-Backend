import factory
from src.apps.identity.models import User
from src.apps.projects.models import Project
from src.core.security import hash_password


class UserFactory(factory.Factory):
    class Meta:
        model = User

    id = factory.Faker("uuid4")
    email = factory.Faker("email")
    hashed_password = hash_password("TestPass123!")
    full_name = factory.Faker("name")
    is_active = True
    is_superadmin = False


class ProjectFactory(factory.Factory):
    class Meta:
        model = Project

    id = factory.Faker("uuid4")
    name = factory.Faker("company")
    code = factory.Sequence(lambda n: f"PRJ-{n:04d}")
    status = "planning"
