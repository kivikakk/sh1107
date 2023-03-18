import pyglet


def vsh(_args):
    window = pyglet.window.Window(width=256, height=256)
    idata = bytearray([0, 10, 50] * 128 * 128)
    img = pyglet.image.ImageData(128, 128, "RGB", bytes(idata))

    @window.event
    def on_draw():
        window.clear()
        img.blit(0, 0, width=256, height=256)

    pyglet.app.run()


class VirtualSH1107:
    pass
