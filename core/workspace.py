class Workspace:
    def __init__(self, workspace_id):
        self.id = workspace_id

if __name__=="__main__":
    ws =Workspace("2")
    print(ws.id)
