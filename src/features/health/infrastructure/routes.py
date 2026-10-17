from uuid import UUID
from fastapi import APIRouter, Depends, Query, Path, Response
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.features.auth.infrastructure.dependencies import require_permission
from src.features.health.domain.dto import ObservationInput, ObservationResponse, ObservationPage, CaseInput, CaseResponse, CasePage, CaseDetail, CaseStatusInput, CaseStatus, HealthHistory, AnimalSummary, DiagnosisInput, DiagnosisResponse, ProductInput, ProductResponse, ProductPage, TreatmentInput, TreatmentResponse, TreatmentCatalogs, ProgramInput, ProgramResponse, ProgramPage, ProgramSchedule, ProgramApplicationInput, ObservationCaseInput, IngredientInput, IngredientResponse, IngredientPage
from .repository import SQLHealthRepository
from .program_repository import SQLProgramRepository
from typing import Literal

router = APIRouter(prefix='/health', tags=['Health management'])

def repository(db: Session = Depends(get_db, scope='function')):
    return SQLHealthRepository(db)

@router.get('/animal-options', response_model=list[AnimalSummary])
def options(q: str = Query('', max_length=100), limit: int = Query(50, ge=1, le=100), actor=Depends(require_permission('health:read')), repo=Depends(repository)):
    return repo.options(q.strip(), limit)

@router.get('/observations', response_model=ObservationPage)
def observations(q: str = Query('', max_length=100), offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100), actor=Depends(require_permission('health:read')), repo=Depends(repository)):
    return repo.observations(q.strip(), offset, limit)

@router.post('/observations', response_model=ObservationResponse, status_code=201)
def create_observation(data: ObservationInput, actor=Depends(require_permission('health:observations:create')), repo=Depends(repository)):
    return repo.create_observation(data, actor)

@router.get('/cases', response_model=CasePage)
def cases(q: str = Query('', max_length=100), status: CaseStatus | None = None, offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100), actor=Depends(require_permission('health:read')), repo=Depends(repository)):
    return repo.cases(q.strip(), status, offset, limit)

@router.post('/cases', response_model=CaseResponse, status_code=201)
def create_case(data: CaseInput, actor=Depends(require_permission('health:cases:write')), repo=Depends(repository)):
    return repo.create_case(data, actor)

@router.get('/cases/{case_id}', response_model=CaseDetail)
def case(case_id: UUID, actor=Depends(require_permission('health:read')), repo=Depends(repository)):
    return repo.detail(str(case_id))

@router.patch('/cases/{case_id}/status', response_model=CaseResponse)
def change_status(case_id: UUID, data: CaseStatusInput, actor=Depends(require_permission('health:cases:write')), repo=Depends(repository)):
    return repo.change_status(str(case_id), data, actor)

@router.get('/animals/{animal_id}/history', response_model=HealthHistory)
def history(animal_id: UUID, actor=Depends(require_permission('health:read')), repo=Depends(repository)):
    return repo.history(str(animal_id))


@router.post('/cases/{case_id}/diagnoses', response_model=DiagnosisResponse, status_code=201)
def create_diagnosis(case_id: UUID, data: DiagnosisInput, actor=Depends(require_permission('health:diagnoses:create')), repo=Depends(repository)):
    return repo.create_diagnosis(str(case_id), data, actor)


@router.get('/catalogs', response_model=TreatmentCatalogs)
def catalogs(actor=Depends(require_permission('health:read')), repo=Depends(repository)):
    return repo.catalogs()

@router.get('/ingredients', response_model=IngredientPage)
def ingredients(q: str = Query('',max_length=120),offset: int = Query(0,ge=0),limit: int = Query(25,ge=1,le=100),actor=Depends(require_permission('health:read')),repo=Depends(repository)):
    return repo.ingredients(q.strip(),offset,limit)


@router.post('/ingredients',response_model=IngredientResponse,status_code=201)
def create_ingredient(data: IngredientInput,actor=Depends(require_permission('health:products:write')),repo=Depends(repository)):
    return repo.save_ingredient(data,actor)


@router.put('/ingredients/{ingredient_id}',response_model=IngredientResponse)
def update_ingredient(data: IngredientInput,ingredient_id: int=Path(gt=0),actor=Depends(require_permission('health:products:write')),repo=Depends(repository)):
    return repo.save_ingredient(data,actor,ingredient_id)


@router.delete('/ingredients/{ingredient_id}',status_code=204)
def delete_ingredient(ingredient_id: int=Path(gt=0),actor=Depends(require_permission('health:products:write')),repo=Depends(repository)):
    repo.delete_ingredient(ingredient_id,actor)
    return Response(status_code=204)


@router.get('/products', response_model=ProductPage, response_model_exclude_unset=True)
def products(q: str = Query('', max_length=150), active: bool | None = None, offset: int = Query(0,ge=0), limit: int = Query(25,ge=1,le=100), actor=Depends(require_permission('health:read')),repo=Depends(repository)):
    result = repo.products(q.strip(),active,offset,limit)
    if 'finance:read' in actor.role.permissions:
        from .pricing import current_prices
        prices = current_prices(repo.db,[p['id'] for p in result['items']])
        for product in result['items']:
            product['current_price'] = prices.get(product['id'])
    return result

@router.post('/products', response_model=ProductResponse, status_code=201)
def create_product(data: ProductInput, actor=Depends(require_permission('health:products:write')),repo=Depends(repository)):
    if data.initial_price and 'finance:write' not in actor.role.permissions:
        from src.core.errors import ApplicationError
        raise ApplicationError('Missing finance permission for product prices',403)
    result = repo.save_product(data,actor)
    if data.initial_price:
        from .pricing import save_price
        save_price(repo.db,result['id'],data.initial_price,actor)
    return result

@router.put('/products/{product_id}',response_model=ProductResponse)
def update_product(product_id: UUID, data: ProductInput, actor=Depends(require_permission('health:products:write')),repo=Depends(repository)):
    if data.initial_price:
        from src.core.errors import ApplicationError
        raise ApplicationError('Use the product price history to add a price',422)
    return repo.save_product(data,actor,str(product_id))

@router.post('/cases/{case_id}/treatments',response_model=TreatmentResponse,status_code=201)
def create_treatment(case_id: UUID,data: TreatmentInput,actor=Depends(require_permission('health:treatments:create')),repo=Depends(repository)):
    return repo.create_treatment(str(case_id),data,actor)


def program_repository(db: Session = Depends(get_db,scope='function')):
    return SQLProgramRepository(db)

@router.get('/programs',response_model=ProgramPage)
def programs(q: str=Query('',max_length=150),active: bool|None=None,offset: int=Query(0,ge=0),limit: int=Query(25,ge=1,le=100),actor=Depends(require_permission('health:read')),repo=Depends(program_repository)):
    return repo.programs(q.strip(),active,offset,limit)

@router.post('/programs',response_model=ProgramResponse,status_code=201)
def create_program(data: ProgramInput,actor=Depends(require_permission('health:programs:write')),repo=Depends(program_repository)):
    return repo.save_program(data,actor)

@router.put('/programs/{program_id}',response_model=ProgramResponse)
def update_program(program_id: UUID,data: ProgramInput,actor=Depends(require_permission('health:programs:write')),repo=Depends(program_repository)):
    return repo.save_program(data,actor,str(program_id))

@router.get('/programs/{program_id}/schedule',response_model=ProgramSchedule)
def schedule(program_id: UUID,q: str=Query('',max_length=100),state: Literal['all','attention','overdue','due','upcoming','scheduled','missing_birth_date']='attention',offset: int=Query(0,ge=0),limit: int=Query(25,ge=1,le=100),actor=Depends(require_permission('health:read')),repo=Depends(program_repository)):
    return repo.schedule(str(program_id),q.strip(),state,offset,limit)

@router.post('/programs/{program_id}/applications',response_model=TreatmentResponse,status_code=201)
def apply_program(program_id: UUID,data: ProgramApplicationInput,actor=Depends(require_permission('health:program_applications:create')),repo=Depends(program_repository)):
    return repo.apply_program(str(program_id),data,actor)


@router.get('/observations/{observation_id}/case-options', response_model=list[CaseResponse])
def observation_cases(observation_id: UUID, q: str = Query('', max_length=100), limit: int = Query(50, ge=1, le=100),
                      actor=Depends(require_permission('health:read')), repo=Depends(repository)):
    return repo.source_cases(str(observation_id), q.strip(), limit)


@router.post('/observations/{observation_id}/case-link', response_model=CaseResponse)
def link_observation(observation_id: UUID, data: ObservationCaseInput,
                     actor=Depends(require_permission('health:cases:write')), repo=Depends(repository)):
    return repo.link_observation(str(observation_id), str(data.case_id), actor)
