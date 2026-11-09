[English](README.md) · **Русский**

# NAM A2 Lite для Line 6 Helix LT

Проект **helix-lt-nam** добавляет блок Neural Amp Modeler (NAM) A2 Lite в прошивку Line 6 Helix LT 3.80.0. Захваты работают на DSP самого Helix LT. В проект также входит **NAM Studio**, локальное приложение для смешивания, объединения в цепочку, переобучения и конвертации захватов.

[Установка и восстановление](helix-lt/INSTALL_RU.md) · [Техническое руководство для Helix LT (на английском)](helix-lt/README.md) · [NAM Studio](#nam-studio)

## Helix LT

**Экспериментальная сборка.** 8 ноября 2026 года её проверили на одном Helix LT. Устройство загрузилось, в меню появился блок **Amp → NAM → NAM A2 Lite**, захват воспроизвёлся. Работу двух блоков NAM на одном пути и фактическую нагрузку на DSP ещё предстоит проверить на Helix LT.

### Сборка

Понадобятся Python 3.10 или новее, Git и оригинальный файл прошивки Helix LT 3.80.0 `Helix_LT_v3.80.0_0x7d01f5efb.hxf`. При сборке проверяется его контрольная сумма MD5 `7505704bd858864e38147e776b3cb7b2`.

```sh
git clone https://github.com/andreidevs/helix-lt-nam
cd helix-lt-nam
python -m pip install numpy capstone
git clone https://github.com/savedadodo/helix-floor-nam-lite floor-port
git -C floor-port checkout 29aea8169d93151b25db61bf1140969de9d7b916
python helix-lt/lt_port.py floor-port "path/to/Helix_LT_v3.80.0_0x7d01f5efb.hxf"
```

Результат сборки появится в `helix-lt/build/Helix_LT_v3.80.0_NAM2_PERSONAL.hxf`. Ожидаемая контрольная сумма MD5 — `8330973f8b445050b826c093eb4c48b4`. Собранная прошивка предназначена для личного использования.

### Установка и восстановление

Вы устанавливаете модифицированную прошивку на свой риск.

1. Сделайте резервную копию пресетов и импульсов (IR) в HX Edit, затем закройте программу.
2. Сначала проверьте, что можете восстановить оригинальную прошивку. Выключите Helix LT, зажмите футсвичи **6 + 12** (MODE и TAP) и включите питание. В режиме обновления переустановите оригинальную прошивку 3.80.0 через Line 6 Updater в **Offline Mode**. Продолжайте после успешной переустановки.
3. Тем же способом установите собранный файл `Helix_LT_v3.80.0_NAM2_PERSONAL.hxf`. Если устройство не загрузится, повторите шаг 2 с оригинальной прошивкой.

Тестовые сборки, замер циклов DSP и звуковые коды диагностики описаны в [техническом руководстве для Helix LT](helix-lt/README.md). Все шаги сборки, установки и восстановления приведены в [русской инструкции](helix-lt/INSTALL_RU.md).

### Загрузка захвата

1. Преобразуйте трёхканальный захват A2 Lite с частотой 48 кГц во вкладке **«Конвертер»** в NAM Studio или командой ниже. Подойдёт и файл `.nam` с несколькими размерами модели, если в нём есть A2 Lite.

   ```sh
   python tools/nam2ir.py "My Amp.nam" -o "My Amp NAM.wav"
   ```

2. Импортируйте полученный `.wav` в слот **User IR** через HX Edit. На Helix LT добавьте блок **Amp → NAM → NAM A2 Lite** и выставьте номер этого слота параметром **Model**. Начните с одного блока NAM на путь.

Редактируйте пресеты с NAM на самом Helix LT. Сборка для LT использует модель с ID 380, поэтому HX Edit может удалить блоки NAM при перезаписи пресета. Если после смены прошивки пресет открылся пустым, не сохраняйте его и вернитесь к сборке, на которой он был сохранён.

## NAM Studio

NAM Studio открывается в браузере через локальный сервер на `127.0.0.1`. Все захваты обрабатываются на вашем компьютере.

| Вкладка | Что делает |
| --- | --- |
| **Смесь** | Смешивает до трёх захватов, работающих параллельно, в одну модель A2 Lite. |
| **Цепочка** | Обучает одну модель A2 Lite по последовательности захватов, например педалей и усилителя. |
| **Переобучение** | Обучает A2 Lite по более крупной модели, например по модели Full из файла A2 с несколькими размерами. |
| **Конвертер** | Пакетно преобразует совместимые захваты `.nam` в файлы `.wav` для импорта через HX Edit в слоты User IR. |

Для обучения и A/B-сравнения можно использовать встроенный гитарный сигнал или свою DI-запись с частотой 48 кГц. Готовую модель можно сохранить в `.nam` или в `.wav` для слота User IR.

В корне репозитория создайте виртуальное окружение командой `python -m venv .venv` и выполните команды для вашей системы.

```powershell
# Windows
.\.venv\Scripts\python.exe -m pip install numpy torch neural-amp-modeler
.\.venv\Scripts\python.exe tools/nam_studio.py
```

```sh
# macOS and Linux
.venv/bin/python -m pip install numpy torch neural-amp-modeler
.venv/bin/python tools/nam_studio.py
```

Для вкладки «Конвертер» достаточно `numpy`. Для обучения также нужны `torch` и `neural-amp-modeler`.

## HX Stomp, HX Stomp XL и HX Effects

В форке есть сборщик `build.py` из исходного проекта для этих трёх устройств с прошивкой 3.80.0. Инструкции для каждой модели приведены в [README исходного проекта](https://github.com/nocaseguy/hx-stomp-nam-lite/blob/003bc0dc4d0dbb67b46f69e151cd1fbb3ae5e46c/README.md) и в [руководстве по настройке в браузере](https://nocaseguy.github.io/hx-stomp-nam-lite/web/).

На **HX Stomp** сборка через `build.py --customos` добавляет опциональные функции CustomOS, в том числе настройки тюнера, отображение BPM и нагрузки на DSP, а также свою заставку загрузки. Совместную сборку NAM и CustomOS ещё предстоит проверить на устройстве. Подробности в [заметках о прошивке](FIRMWARE_NOTES.md) и [описании ограничений ресурсов](docs/resource-limits.md).

## Авторы и лицензия

- Порт для Helix LT основан на [порте savedadodo для Helix Floor](https://github.com/savedadodo/helix-floor-nam-lite).
- Ядро NAM, инструменты SHARC и сборщик для устройств HX взяты из [hx-stomp-nam-lite от Derek Bui](https://github.com/nocaseguy/hx-stomp-nam-lite).
- Формат захватов разработан для [Neural Amp Modeler Стивена Аткинсона](https://github.com/sdatkinson/neural-amp-modeler).
- Опциональные функции CustomOS взяты из [hx-stomp-customOS от wisemandenny](https://github.com/wisemandenny/hx-stomp-customOS).

Исходный код распространяется по лицензии GPL-3.0-or-later. См. [LICENSE](LICENSE), [NOTICE](NOTICE) и [журнал изменений](CHANGELOG.md).
