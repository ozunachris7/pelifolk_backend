from datetime import date
from sqlalchemy import func, or_, select
from src.core.models import AnimalModel
from src.features.animals.domain.dto import AncestorResponse, GenealogyResponse
from .repository import SQLAnimalRepository


def genealogy(db, animal_id, offset, limit):
    repo = SQLAnimalRepository(db)
    root = repo._row(animal_id)
    # Two ancestor generations are bounded even if legacy data contains a cycle.
    # Shared ancestors remain present in both branches rather than being discarded.
    def ancestor(animal, generations):
        if animal is None:
            return None
        return AncestorResponse(
            animal=repo._response(animal),
            mother=ancestor(db.get(AnimalModel, animal.mother_id), generations - 1) if generations and animal.mother_id else None,
            father=ancestor(db.get(AnimalModel, animal.father_id), generations - 1) if generations and animal.father_id else None)

    query = select(AnimalModel).where(or_(AnimalModel.mother_id == animal_id, AnimalModel.father_id == animal_id))
    counts = dict(db.execute(query.with_only_columns(AnimalModel.sex, func.count()).group_by(AnimalModel.sex)).all())
    children = db.scalars(query.order_by(AnimalModel.birth_date.desc(), AnimalModel.name, AnimalModel.id).offset(offset).limit(limit))
    return GenealogyResponse(as_of=date.today(), tree=ancestor(root, 2),
                             children=[repo._response(child) for child in children],
                             total_children=sum(counts.values()), female_children=counts.get('female', 0),
                             male_children=counts.get('male', 0), offset=offset, limit=limit)
