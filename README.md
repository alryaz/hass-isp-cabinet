# Провайдеры Интернет для Home Assistant
> Предоставление информации о текущем состоянии ваших лицевых счетов провайдеров интернет.
>
>[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
>[![Лицензия](https://img.shields.io/badge/%D0%9B%D0%B8%D1%86%D0%B5%D0%BD%D0%B7%D0%B8%D1%8F-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
>[![Поддержка](https://img.shields.io/badge/%D0%9F%D0%BE%D0%B4%D0%B4%D0%B5%D1%80%D0%B6%D0%B8%D0%B2%D0%B0%D0%B5%D1%82%D1%81%D1%8F%3F-%D0%B4%D0%B0-green.svg)](https://github.com/alryaz/hass-isp-cabinet/graphs/commit-activity)
>
>[![Пожертвование Yandex](https://img.shields.io/badge/%D0%9F%D0%BE%D0%B6%D0%B5%D1%80%D1%82%D0%B2%D0%BE%D0%B2%D0%B0%D0%BD%D0%B8%D0%B5-Yandex-red.svg)](https://money.yandex.ru/to/410012369233217)
>[![Пожертвование PayPal](https://img.shields.io/badge/%D0%9F%D0%BE%D0%B6%D0%B5%D1%80%D1%82%D0%B2%D0%BE%D0%B2%D0%B0%D0%BD%D0%B8%D0%B5-Paypal-blueviolet.svg)](https://www.paypal.me/alryaz)

## Поддерживаемые провайдеры
Все провайдеры поддерживают следующие атрибуты:
- `code`: Номер лицевого счёта
- `current_balance`: Текущий баланс
- `tariff_name`: Название тарифа
- `tariff_speed`: Скорость тарифа
- `tariff_speed_unit`: Мера исчисления скорости
- `tariff_monthly_cost`: Ежемесячная стоимость тарифа

Также отдельные провайдеры поддерживают набор дополнительных атрибутов:

<a name="providers_table"></a>
| _Название_ | _Идентификатор_ | Рекомендуемый платёж<br>`payment_suggested` | Требуемый платёж<br>`payment_required`   | Бонусы<br>`bonuses`    | Адрес<br>`address`     | Клиент<br>`client`
|-|-|-|-|-|-|-|
| [Almatel<br>Альмател](https://almatel.ru) | `almatel`<br>`2kom` | Да<sup>1</sup> | Да | Да | Да | Да
| [SevenSky<br>ГорКом](https://seven-sky.net) | `sevensky`<br>`gorcom` | Да<sup>1</sup> | Да | Нет | Да | Да |
| [Sky Engineering](http://sky-en.ru) | `sky_engineering` | Да | Нет | Нет | Нет | Да |
| [МГТС](https://mgts.ru) | `mgts`<br>`mts` | Да<sup>1</sup> | Да | Нет | Нет | Да
| Акадо | _в разработке_ |

<sup>1</sup> Атрибут вычисляется посредством вычета текущего состояния баланса из ежемесячной стоимости тарифа.

## Установка
### Посредством HACS
1. Откройте HACS (через `Extensions` в боковой панели)
1. Добавьте новый произвольный репозиторий:
   1. Выберите `Integration` (`Интеграция`) в качестве типа репозитория
   1. Введите ссылку на репозиторий: `https://github.com/alryaz/hass-isp-cabinet`
   1. Нажмите кнопку `Add` (`Добавить`)
   1. Дождитесь добавления репозитория (занимает до 10 секунд)
   1. Теперь вы должны видеть доступную интеграцию `ISP Cabinet` в списке новых интеграций.
1. Нажмите кнопку `Install` чтобы увидеть доступные версии
1. Установите последнюю версию нажатием кнопки `Install`
1. Перезапустите HomeAssistant

_Примечание:_ Не рекомендуется устанавливать ветку `master`. Она используется исключительно для разработки. 

### Вручную
Клонируйте репозиторий во временный каталог, затем создайте каталог `custom_components` внутри папки конфигурации
вашего HomeAssistant (если она еще не существует). Затем переместите папку `isp_cabinet` из папки `custom_components` 
репозитория в папку `custom_components` внутри папки конфигурации HomeAssistant.
Пример (при условии, что конфигурация HomeAssistant доступна по адресу `/mnt/homeassistant/config`) для Unix-систем:
```
git clone https://github.com/alryaz/hass-isp-cabinet.git hass-isp-cabinet
mkdir -p /mnt/homeassistant/config/custom_components
mv hass-isp-cabinet/custom_components/isp_cabinet /mnt/homeassistant/config/custom_components
```

## Конфигурация
### Через интерфейс HomeAssistant
1. Откройте `Настройки` -> `Интеграции`
1. Нажмите внизу справа страницы кнопку с плюсом
1. Введите в поле поиска `ISP Cabinet` или `ЛК Интернет-провайдера`
   1. Если по какой-то причине интеграция не была найдена, убедитесь, что HomeAssistant был перезапущен после
        установки интеграции.
1. Выберите первый результат из списка
1. Выберите требуемого провайдера и введите данные вашей учётной записи для входа в личный кабинет
1. Нажмите кнопку `Продолжить`
1. Через несколько секунд начнётся обновление; проверяйте список ваших объектов на наличие
   объектов, чьи названия выглядят как `<имя провайдера> <номер лицевого счёта>`.
   
### Через `configuration.yaml`
#### Базовая конфигурация
Для настройки данной интеграции потребуются данные авторизации в ЛК Мосэнергосбыт.  
`isp` - Идентификатор провайдера ([см. выше](#providers_table))  
`username` - Имя пользователя (телефон / адрес эл. почты)  
`password` - Пароль
```yaml
isp_cabinet:
  isp: my_internet_provider
  username: !secret my_internet_provider_username
  password: !secret my_internet_provider_password
```

#### Несколько пользователей
Возможно добавить несколько пользователей.
Для этого вводите данные, используя пример ниже:
```yaml
isp_cabinet:
    # First account
  - isp: first_provider
    username: !secret first_provider_username
    password: !secret first_provider_password

    # Second account
  - isp: second_provider
    username: !secret second_provider_username
    password: !secret second_provider_password

    # Third account
  - isp: third_provider
    username: !secret third_provider_username
    password: !secret third_provider_password 
```

#### Изменение интервалов обновления
Если по какой-то причине Вам требуется обновлять данные чаще, чем по умолчанию,
Вы можете переопределить интервал обновления одним из следующих образов:
```yaml
isp_cabinet:
  ...
  # Интервал обновления данных
  scan_interval:
    hours: 6
    seconds: 3
    minutes: 1
    ...

  # ... также возможно задать секундами
  scan_interval: 21600
```