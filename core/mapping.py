class WorkspaceMapping:
    def __init__(self):
        self.mapping = {}

    def set(self, workspace_id, wallpaper):
        self.mapping[workspace_id] = wallpaper

    def get(self, workspace_id):
        return self.mapping.get(workspace_id)


if __name__ == "__main__":
    mapping = WorkspaceMapping()

    mapping.set("1", "/home/karan/Pictures/wallpapers/Red_Eclipse.png")
    mapping.set("2", "/home/karan/Pictures/wallpapers/Relaxed_Mario.png")
    mapping.set("3", "/home/karan/Pictures/wallpapers/Resthouse.png")
    mapping.set("4", "/home/karan/Pictures/wallpapers/Retro - Programmer.jpeg")
    mapping.set("5", "/home/karan/Pictures/wallpapers/Riding in a bus.png")
    mapping.set("6", "/home/karan/Pictures/wallpapers/River-Moutains-Cherry-Blosums.png")
    mapping.set("7", "/home/karan/Pictures/wallpapers/River.png")
    mapping.set("8", "/home/karan/Pictures/wallpapers/rocks_in_the_water.jpg")
    mapping.set("9", "/home/karan/Pictures/wallpapers/Scifi-Room.png")
    mapping.set("10", "/home/karan/Pictures/wallpapers/sea1.jpg")

    print(mapping.get("1"))
    print(mapping.get("10"))