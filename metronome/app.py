import os
import webview
from .api import MetronomeAPI


def main():
    api = MetronomeAPI()

    ui_path = os.path.join(os.path.dirname(__file__), '..', 'ui', 'index.html')
    ui_path = os.path.abspath(ui_path)

    window = webview.create_window(
        title='Metronome',
        url=f'file://{ui_path}',
        js_api=api,
        width=400,
        height=580,
        min_size=(360, 540),
        background_color='#0D0D0D',
        resizable=True,
    )

    api.set_window(window)
    webview.start(debug=False)


if __name__ == '__main__':
    main()
