from pydantic import BaseModel, Field


class success(BaseModel):
    code:str = "200"
    message:str = "ok"
    data:dict= Field(default_factory=dict)

class error(BaseModel):
    code:str = "400"
    message:str = "error"
    data:dict

