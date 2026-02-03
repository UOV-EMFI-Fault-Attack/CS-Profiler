#ifndef GPIO_H
#define GPIO_H

#include <stdint.h>

/* -----------------------------
 * STM32F4 GPIO Base Addresses
 * ----------------------------- */
#define GPIOA 0x40020000UL
#define GPIOB 0x40020400UL
#define GPIOC 0x40020800UL
#define GPIOD 0x40020C00UL
#define GPIOE 0x40021000UL
#define GPIOF 0x40021400UL
#define GPIOG 0x40021800UL
#define GPIOH 0x40021C00UL
#define GPIOI 0x40022000UL

/* -----------------------------
 * GPIO Register Offsets
 * ----------------------------- */
#define GPIO_MODER_OFFSET   0x00
#define GPIO_OTYPER_OFFSET  0x04
#define GPIO_OSPEEDR_OFFSET 0x08
#define GPIO_PUPDR_OFFSET   0x0C
#define GPIO_IDR_OFFSET     0x10
#define GPIO_ODR_OFFSET     0x14
#define GPIO_BSRR_OFFSET    0x18
#define GPIO_LCKR_OFFSET    0x1C

/* -----------------------------
 * Register Access Macros
 * ----------------------------- */
#define REG32(addr) (*(volatile uint32_t *)(addr))

#define GPIO_MODER(port)    REG32((port) + GPIO_MODER_OFFSET)
#define GPIO_OTYPER(port)   REG32((port) + GPIO_OTYPER_OFFSET)
#define GPIO_OSPEEDR(port)  REG32((port) + GPIO_OSPEEDR_OFFSET)
#define GPIO_PUPDR(port)    REG32((port) + GPIO_PUPDR_OFFSET)
#define GPIO_IDR(port)      REG32((port) + GPIO_IDR_OFFSET)
#define GPIO_ODR(port)      REG32((port) + GPIO_ODR_OFFSET)
#define GPIO_BSRR(port)     REG32((port) + GPIO_BSRR_OFFSET)
#define GPIO_LCKR(port)     REG32((port) + GPIO_LCKR_OFFSET)

/* Mask for the 2 bits corresponding to pin n in MODER or PUPDR */
#define GPIO_MODE_MASK(pin)   (0x3 << ((pin) * 2))
#define GPIO_PUPD_MASK(pin)   (0x3 << ((pin) * 2))

/* Shift mode/pupd value into the correct position for pin n */
#define GPIO_MODE(pin, mode)  ((mode & 0x3) << ((pin) * 2))
#define GPIO_PUPD(pin, pupd)  ((pupd & 0x3) << ((pin) * 2))


/* -----------------------------
 * GPIO Pin Macros
 * ----------------------------- */
#define GPIO0   (1u << 0)
#define GPIO1   (1u << 1)
#define GPIO2   (1u << 2)
#define GPIO3   (1u << 3)
#define GPIO4   (1u << 4)
#define GPIO5   (1u << 5)
#define GPIO6   (1u << 6)
#define GPIO7   (1u << 7)
#define GPIO8   (1u << 8)
#define GPIO9   (1u << 9)
#define GPIO10  (1u << 10)
#define GPIO11  (1u << 11)
#define GPIO12  (1u << 12)
#define GPIO13  (1u << 13)
#define GPIO14  (1u << 14)
#define GPIO15  (1u << 15)

/* -----------------------------
 * GPIO Modes
 * ----------------------------- */
#define GPIO_MODE_INPUT     0x00
#define GPIO_MODE_OUTPUT    0x01
#define GPIO_MODE_AF        0x02
#define GPIO_MODE_ANALOG    0x03

/* -----------------------------
 * GPIO Pull-up / Pull-down
 * ----------------------------- */
#define GPIO_PUPD_NONE      0x00
#define GPIO_PUPD_PULLUP    0x01
#define GPIO_PUPD_PULLDOWN  0x02


/* Configure GPIO pin(s) mode and pull-up/pull-down */
static inline void inline_gpio_mode_setup(uint32_t gpioport, uint8_t mode, uint8_t pull_up_down, uint16_t gpios)
{
	uint16_t i;
	uint32_t moder, pupd;

	/*
	 * We want to set the config only for the pins mentioned in gpios,
	 * but keeping the others, so read out the actual config first.
	 */
	moder = GPIO_MODER(gpioport);
	pupd = GPIO_PUPDR(gpioport);

	for (i = 0; i < 16; i++) {
		if (!((1 << i) & gpios)) {
			continue;
		}

		moder &= ~GPIO_MODE_MASK(i);
		moder |= GPIO_MODE(i, mode);
		pupd &= ~GPIO_PUPD_MASK(i);
		pupd |= GPIO_PUPD(i, pull_up_down);
	}

	/* Set mode and pull up/down control registers. */
	GPIO_MODER(gpioport) = moder;
	GPIO_PUPDR(gpioport) = pupd;
}


/** @brief Set one or more GPIO pins high
 *
 * @param[in] gpioport Base address of GPIO port
 * @param[in] gpios Pin mask (e.g., GPIO5 | GPIO12)
 */
static inline void inline_gpio_set(uint32_t gpioport, uint16_t gpios)
{
    GPIO_BSRR(gpioport) = gpios;
}

/** @brief Clear one or more GPIO pins (set low)
 *
 * @param[in] gpioport Base address of GPIO port
 * @param[in] gpios Pin mask
 */
static inline void inline_gpio_clear(uint32_t gpioport, uint16_t gpios)
{
	GPIO_BSRR(gpioport) = (gpios << 16);
}



/*---------------------------------------------------------------------------*/
/** @brief Get the current state of one or more GPIO pins
 *
 * @param[in] gpioport Base address of GPIO port
 * @param[in] gpios Pin mask
 * @return Mask of pins that are currently high
 */
// uint16_t stm32_gpio_get(uint32_t gpioport, uint16_t gpios)
// {
//     return (uint16_t)(GPIO_IDR(gpioport) & gpios);
// }

/*---------------------------------------------------------------------------*/
/** @brief Read entire GPIO port
 *
 * @param[in] gpioport Base address of GPIO port
 * @return 16-bit value of input data register
 */
// uint16_t stm32_gpio_port_read(uint32_t gpioport)
// {
//     return (uint16_t)(GPIO_IDR(gpioport) & 0xFFFF);
// }

/*---------------------------------------------------------------------------*/
/** @brief Write entire GPIO port
 *
 * @param[in] gpioport Base address of GPIO port
 * @param[in] data 16-bit output value
 */
// void stm32_gpio_port_write(uint32_t gpioport, uint16_t data)
// {
//     GPIO_ODR(gpioport) = data;
// }

#endif /* GPIO_H */
