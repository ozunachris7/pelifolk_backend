"""Compare recorded parents and grandparents, without estimating genetic scores."""
from src.core.errors import ApplicationError
from src.core.models import AnimalModel
from sqlalchemy import select


def check_kinship(db, female_id, male_id, *, lock=False):
    if female_id == male_id:
        raise ApplicationError('Mating animals must be different', 422)
    cache = {}

    def get(animal_id):
        if animal_id not in cache:
            query = select(AnimalModel).where(AnimalModel.id == animal_id).execution_options(populate_existing=True)
            cache[animal_id] = db.scalar(query.with_for_update() if lock else query)
        return cache[animal_id]

    female, male = get(female_id), get(male_id)
    if female is None or male is None:
        raise ApplicationError('Animal not found', 404)
    if female.sex != 'female' or male.sex != 'male':
        raise ApplicationError('Reproductive animal sex is incompatible', 422)

    def summary(a):
        return dict(id=a.id, name=a.name, siniiga=a.siniiga, sex=a.sex)

    invalid = False

    def lineage(root):
        paths = {root.id: ['self']}
        missing = []

        def visit(animal, path, ancestors):
            nonlocal invalid
            for role, expected_sex in [('mother','female'), ('father','male')]:
                slot = '.'.join([*path,role])
                parent_id = getattr(animal, role + '_id') if animal else None
                parent = get(parent_id) if parent_id else None
                if parent and (parent.id in ancestors or parent.sex != expected_sex):
                    invalid = True
                    parent = None
                if parent:
                    paths.setdefault(parent.id,[]).append(slot)
                else:
                    missing.append(slot)
                if not path:
                    visit(parent, [role], ancestors | ({parent.id} if parent else set()))
        visit(root, [], {root.id})
        return paths, missing

    female_paths, missing_female = lineage(female)
    male_paths, missing_male = lineage(male)
    matches = []
    for ancestor_id in sorted(female_paths.keys() & male_paths.keys()):
        fp, mp = female_paths[ancestor_id], male_paths[ancestor_id]
        female_depth = min(0 if p == 'self' else len(p.split('.')) for p in fp)
        male_depth = min(0 if p == 'self' else len(p.split('.')) for p in mp)
        if min(female_depth,male_depth) == 0:
            kind = 'direct_ancestor'
        elif female_depth == male_depth == 1:
            kind = 'shared_parent'
        elif female_depth == male_depth == 2:
            kind = 'shared_grandparent'
        else:
            kind = 'parent_grandparent'
        matches.append(dict(kind=kind, ancestor=summary(cache[ancestor_id]), female_paths=fp, male_paths=mp))
    complete = not missing_female and not missing_male and not invalid
    return dict(female=summary(female), male=summary(male), depth=2,
        status='related' if matches else 'no_relationship_found' if complete else 'insufficient_data',
        lineage_complete=complete, invalid_lineage=invalid,
        missing_female=missing_female, missing_male=missing_male, matches=matches)
