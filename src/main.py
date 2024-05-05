#!/usr/bin/env python3
import datetime
import itertools
import logging
import pathlib
import random
import sys

import constants
import pygame

# TODO:
# current score in top right
# damage bar
# turret pewpew
# mask collision with ship
# circle collision with Bawlers
# you lose animation / Dead Screen
# clickable, focusable esc menu and title menu
# top scores and entry (main/esc menus?)
# drops and collecting
# settings menu
# Real sounds, sound design
# Terrorangles triable baddies
# Diamonds baddies
# New Bawler types
# endless screen
# nebula background
# Camera that follows player at edges
# off-screen spawn

log = logging.getLogger('PPoD')

load_image = None  # function to load images, set by Game().
load_sheet = None  # function to load sprite sheets, set by Game().

ASSETS_PATH = pathlib.Path('assets')
DELTA_DIVISOR = 2000  # how much (velocity * timedelta) is divided by
DEBUG_CYCLE = (x == 0 for x in itertools.cycle(range(40)))  # True every 40 frames
ANGLE_45_TO_FACING = {
    0: 0,
    1: 4,
    2: 1,
    3: 5,
    4: 2,
    5: 6,
    6: 3,
    7: 7,
    8: 0,
}
POLAR_45_TO_FACING = {
    0: 1,
    1: 4,
    2: 2,
    3: 5,
    4: 3,
    5: 6,
    6: 0,
    7: 7,
    8: 0,
}


def rotated_8xarray(image):
    """Return tuple of image (facing up) rotated in eight facings (u, r, d, l, ur, dr, dl, ul."""
    return (
        # up, right, down, left
        image.convert_alpha(),
        pygame.transform.rotate(image, -90).convert_alpha(),
        pygame.transform.rotate(image, 180).convert_alpha(),
        pygame.transform.rotate(image, 90).convert_alpha(),
        # ur, dr, dl, ul
        pygame.transform.rotate(image, -45).convert_alpha(),
        pygame.transform.rotate(image, -135).convert_alpha(),
        pygame.transform.rotate(image, 135).convert_alpha(),
        pygame.transform.rotate(image, 45).convert_alpha(),
    )


class Config:
    # 4:3 aspect ratio 400x300, 800x600, 960x720, 1024x768, 1280x960, 1400x1050, 1440x1080, 1600x1200, 1856x1392, 1920x1440, 2048x1536
    # 16:9 aspect ratio 640x360, 1024x576, 1152x648, 1280x720 (HD), 1366x768, 1600x900, 1920x1080 (FHD), 2560x1440 (QHD), 3840x2160 (4K), 7680x4320 (8K)
    #SIZES = [(640, 360, 1), (1280, 720, 2), (1920, 1080, 3), (3840, 2160, 6)]
    #SIZES = [(960, 720, 1), (1920, 1440, 2)]
    SIZES = [(640, 480, 1), (1280, 960, 2), (1920, 1440, 3)]

    def __init__(self):
        self.resolution = 1
        self.fullscreen = False
        self.sound = 0.2
        self.music = 0.7

    @property
    def music(self):
        return self._music

    @music.setter
    def music(self, volume):
        self._music = volume
        pygame.mixer.music.set_volume(volume)

    @property
    def resolution(self):
        return (self.width, self.height)

    @resolution.setter
    def resolution(self, resolution):
        if resolution < 0 or resolution > len(self.SIZES):
            print('Invalid resolution, must be between 1 and', len(self.SIZES))
            resolution = 1
        self.width, self.height, self.scale_factor = self.SIZES[resolution - 1]
        self.display_rect = pygame.Rect(0, 0, self.width, self.height)


class Timer:
    def __init__(self, duration):
        """@param duration: milliseconds or iterable of milliseconds."""
        if isinstance(duration, int | float):
            duration = itertools.repeat(duration)
        self.duration = duration
        self.timer = 0

    def __call__(self, timedelta):
        """Returns True every milliseconds."""
        self.timer -= timedelta
        if self.timer <= 0:
            self.timer += next(self.duration)
            return True
        return False


class Animation(Timer):
    def __init__(self, duration, images):
        super().__init__(duration)
        self._images = images
        self.reset()

    def __call__(self, timedelta):
        if not self.complete and super().__call__(timedelta):
            try:
                return next(self.images)
            except StopIteration:
                self.complete = True

    def reset(self):
        self.complete = False
        self.timer = 0
        self.first = self._images[0]
        self.images = iter(self._images)

    def copy(self):
        return Animation(self.duration, self._images)


class PlayerSprite(pygame.sprite.Sprite):
    def __init__(self, config):
        super().__init__()
        self.bounds = config.display_rect
        scale = config.scale_factor
        self.weapons = list()
        self.health = 100
        self.speed = 200 * scale  # max velocity
        self.accel = 3 * scale  # accelleration
        self.damping = 1 * scale  # speed slow down
        self._dx = 0
        self._dy = 0
        self.facing = 0
        self._facing_locked = False
        self._images = rotated_8xarray(load_image('ship.png'))
        self.image = self._images[self.facing]
        self.rect = self.image.get_frect()
        self.rect.center = self.bounds.center
        self.sound_hit = pygame.mixer.Sound(ASSETS_PATH / 'sfx' / 'playerhit.wav')

    def take_damage(self, damage_type, damage):
        self.sound_hit.play(0, 0, 0)
        self.health -= damage
        if self.health <= 0:
            pygame.event.post(pygame.event.Event(constants.DEAD))
            self.kill()

    def addweapon(self, weapon):
        self.weapons.append(weapon)

    def update(self, timedelta, baddies):
        speed = (self.speed * timedelta) / DELTA_DIVISOR
        dv = (self.accel * timedelta) / DELTA_DIVISOR
        # input
        keys = pygame.key.get_pressed()
        up = keys[pygame.K_UP] or keys[pygame.K_w] or keys[pygame.K_KP8]
        right = keys[pygame.K_RIGHT] or keys[pygame.K_d] or keys[pygame.K_KP6]
        down = keys[pygame.K_DOWN] or keys[pygame.K_s] or keys[pygame.K_KP2]
        left = keys[pygame.K_LEFT] or keys[pygame.K_a] or keys[pygame.K_KP4]
        if up and not down:
            self._dy -= dv
        elif down:
            self._dy += dv
        else:  # dampen vertical velocity
            damp = (self.damping * timedelta) / DELTA_DIVISOR
            if self._dy > 0:
                self._dy = max(0, self._dy - damp)
            elif self._dy < 0:
                self._dy = min(0, self._dy + damp)
        if left and not right:
            self._dx -= dv
        elif right:
            self._dx += dv
        else:  # dampen horizontal velocity
            damp = (self.damping * timedelta) / DELTA_DIVISOR
            if self._dx > 0:
                self._dx = max(0, self._dx - damp)
            elif self._dx < 0:
                self._dx = min(0, self._dx + damp)
        pygame.math.clamp(self._dy, -speed, speed)
        pygame.math.clamp(self._dx, -speed, speed)
        just = pygame.key.get_just_pressed()
        if just[pygame.K_UP] or just[pygame.K_w] or just[pygame.K_KP8]:
            self.facing = 0
        if just[pygame.K_RIGHT] or just[pygame.K_d] or just[pygame.K_KP6]:
            self.facing = 1
        if just[pygame.K_DOWN] or just[pygame.K_s] or just[pygame.K_KP2]:
            self.facing = 2
        if just[pygame.K_LEFT] or just[pygame.K_a] or just[pygame.K_KP4]:
            self.facing = 3
        # calculate
        self.rect.x += self._dx
        self.rect.y += self._dy
        self.image = self._images[self.facing]
        # keep in bounds
        if self.rect.bottom > self.bounds.bottom:
            self.rect.bottom = self.bounds.bottom
            self._dy = 0
        if self.rect.top < self.bounds.top:
            self.rect.top = self.bounds.top
            self._dy = 0
        if self.rect.right > self.bounds.right:
            self.rect.right = self.bounds.right
            self._dx = 0
        if self.rect.left < self.bounds.left:
            self.rect.left = self.bounds.left
            self._dx = 0

        for x in self.weapons:
            x.fire(timedelta, self.rect, self.facing, baddies)


class PewPewCannon:
    def __init__(self, config, group, rof=500, life=400, speed=800):
        """
        @param group: sprite group to add projectiles to.
        @param rof: rate of fire every x milliseconds.
        @param life: life of projectile in milliseconds.
        @param speed: speed of projectile in scaled pixels per ms/DELTA_DIVISOR.
        """
        scale = config.scale_factor
        self.sprite_group = group
        self._rof = Timer(rof)
        self._damage = ('pewpew', 10)
        self._life = life
        self._init_cannons(scale, speed)
        self.sound = pygame.mixer.Sound(ASSETS_PATH / 'sfx' / 'pewpew.wav')
        self.sound.set_volume(config.sound / 2)

    def _pew_pew_image(self, scale):
        length = 8 * scale
        width = 1 * scale
        mid = length // 2
        halfgap = 1 * scale
        head = 1 * scale
        self.rect = pygame.FRect(0, 0, width, length)
        pew_pew = pygame.Surface((width, length), flags=pygame.SRCALPHA)
        # draw dashed line from bottom to top
        pygame.draw.line(pew_pew, (10, 205, 10), (0, length), (0, mid + halfgap), width)
        pygame.draw.line(pew_pew, (10, 205, 10), (0, mid - halfgap), (0, 0), width)
        pygame.draw.line(pew_pew, (140, 255, 140), (0, mid + halfgap + head), (0, mid + halfgap), width)
        pygame.draw.line(pew_pew, (140, 255, 140), (0, head), (0, 0), width)
        return pew_pew

    def _init_cannons(self, scale, speed):
        self._images = rotated_8xarray(self._pew_pew_image(scale))
        self._pewports = itertools.cycle(
            (
                (
                    (14 * scale, 9 * scale),
                    (16 * scale, 14 * scale),
                    (17 * scale, 16 * scale),
                    (9 * scale, 14 * scale),
                    (23 * scale, 7 * scale),
                    (15 * scale, 7 * scale),
                    (15 * scale, 7 * scale),
                    (15 * scale, 7 * scale),
                ),
                (
                    (17 * scale, 9 * scale),
                    (16 * scale, 17 * scale),
                    (14 * scale, 16 * scale),
                    (9 * scale, 17 * scale),
                    (25 * scale, 10 * scale),
                    (17 * scale, 7 * scale),
                    (17 * scale, 7 * scale),
                    (17 * scale, 7 * scale),
                ),
            ),
        )
        speed *= scale  # of projectile
        self._dv = [  # dx, dy of projectile for each facing
            (0, -1 * speed),
            (1 * speed, 0),
            (0, 1 * speed),
            (-1 * speed, 0),
            (1 * speed, -1 * speed),
            (1 * speed, 1 * speed),
            (-1 * speed, 1 * speed),
            (-1 * speed, -1 * speed),
        ]

    def fire(self, timedelta, ship_rect, facing, baddies):
        """If rof timer is up, fire a projectile towards facing from upper left.

        @param timedelta: milliseconds since last update.
        @param ship_rect: Rect of the firing sprite.
        @param facing: of the firing sprite.
        @param baddies: sprite group of baddies.
        """
        if self._rof(timedelta):
            px, py = next(self._pewports)[facing]
            image = self._images[facing]
            rect = self.rect.move(ship_rect.x + px, ship_rect.y + py)  # returns new Rect()
            p = PewPew(*self._dv[facing], image, rect, self._life, self._damage)
            self.sprite_group.add(p)
            self.sound.play(0, 0, 10)


class PewPewTurret(PewPewCannon):
    def __init__(self, config, group, rof=itertools.cycle((1000, 80)), life=400, speed=800, rotation=360):
        super().__init__(config, group, rof, life, speed)
        self._rotation = rotation

    def _init_cannons(self, scale, speed):
        self._images = rotated_8xarray(self._pew_pew_image(scale))
        speed *= scale  # of projectile
        self.speed = speed

    def fire(self, timedelta, ship_rect, facing, baddies):
        if self._rof(timedelta):
            if not baddies:
                return
            cannon = pygame.Vector2(ship_rect.center)
            closest_distance = 100000
            for x in baddies:
                target = pygame.Vector2(x.rect.center)
                distance = cannon.distance_to(target)
                if distance < closest_distance:
                    closest_distance = distance
                    closest_target = target
            dv = (closest_target - cannon).normalize() * self.speed
            po = dv.as_polar()[1] + 180
            # ic(angle, cannon, dv, po, closest_distance)
            image = self._images[ANGLE_45_TO_FACING[po // 45]]
            rect = image.get_rect()
            rect.center = ship_rect.center
            p = PewPew(*dv.xy, image, rect, self._life, self._damage)
            self.sprite_group.add(p)
            self.sound.play(0, 0, 10)


class PewPew(pygame.sprite.Sprite):
    """Projectiles do not take damage, are destroyed on collision."""

    def __init__(self, dx, dy, image, rect, life, damage):
        super().__init__()
        self.dx = dx
        self.dy = dy
        self.rect = rect
        self.image = image
        self.life = life
        self.damage_type, self.damage_amount = damage

    def update(self, timedelta):
        self.life -= timedelta
        if self.life < 0:
            self.kill()
            return
        self.rect.x += (self.dx * timedelta) / DELTA_DIVISOR
        self.rect.y += (self.dy * timedelta) / DELTA_DIVISOR

    def impact(self, target):
        """If target takes/absorbs damage, kill."""
        if target.take_damage(self.damage_type, self.damage_amount):
            self.kill()


class StaticAnimation(pygame.sprite.Sprite):
    def __init__(self, group, animation, x, y):
        super().__init__()
        self.add(group)
        self.animation = animation
        self.image = animation.first
        self.rect = self.image.get_frect()
        self.rect.center = (x, y)

    def update(self, timedelta):
        if self.animation.complete:
            self.kill()
            return
        if image := self.animation(timedelta):
            self.image = image


class BawlerSpawner:
    def __init__(self, config, explosion_group):
        self.baddie = Bawler
        self.baddie.bounds = config.screen_bounds
        self.explosion_group = explosion_group
        self.explosion_animation = Animation(80, load_sheet('bawler_explosion.png', 32, 32))
        self.explosion_sound = pygame.mixer.Sound(ASSETS_PATH / 'sfx' / 'bawlerboom.wav')
        self.explosion_sound.set_volume(config.sound)
        self.variations = self._make_variations(config.scale_factor)

    def __call__(self, x, y):
        """Spawn a Bawler centered at x, y."""
        return self.baddie(x, y, *random.choice(self.variations))

    def _make_variations(self, scale):
        variations = list()
        explosion = lambda x, y: StaticAnimation(self.explosion_group, self.explosion_animation.copy(), x, y)
        for power in (4, 4, 6, 6, 8):
            health = power // 4
            damage = ('impact', power // 2)
            radius = power * scale
            dx = dy = abs((10 - radius) // 2) * 10 * scale
            image = pygame.Surface((radius * 2, radius * 2), flags=pygame.SRCALPHA).convert_alpha()
            rect = image.get_rect()
            pygame.draw.circle(image, (220, 0, 0), rect.center, radius)
            pygame.draw.circle(image, (200, 100, 0), rect.center, radius, width=1 * scale)
            variations.append((dx, dy, image, (explosion, self.explosion_sound), health, damage, radius))
        return tuple(variations)


class Bawler(pygame.sprite.Sprite):
    seq = itertools.count(1)

    def __init__(self, x, y, dx, dy, image, death, health, damage, radius):
        super().__init__()
        self._dx = dx
        self._dy = dy
        self.image = image
        self.death_animation, self.death_sound = death
        self.health = health
        self.damage = damage
        self.radius = radius
        self.id = next(self.seq)
        self.rect = self.image.get_frect()
        self.rect.center = (x, y)
        self.wiggle = (-int(self.rect.width / 4), int(self.rect.width / 4))

    def take_damage(self, damage_type, damage):
        """Return amount of damage taken."""
        self.health -= damage
        if self.health <= 0:
            self.death_animation(*self.rect.center)
            self.death_sound.play(0, 0, 0)
            self.kill()
            return damage
        return 0

    def impact(self, target):
        """Collide with target, target takes damage, self destroyed."""
        if self.health > 0:
            target.take_damage(*self.damage)
        self.kill()

    def update(self, timedelta, target):
        tx, ty = target.rect.center
        x, y = self.rect.center
        self._dx += random.randint(*self.wiggle)
        self._dy += random.randint(*self.wiggle)
        if x < tx:
            x += (self._dx * timedelta) / DELTA_DIVISOR
        elif x > tx:
            x -= (self._dx * timedelta) / DELTA_DIVISOR
        if y < ty:
            y += (self._dy * timedelta) / DELTA_DIVISOR
        elif y > ty:
            y -= (self._dy * timedelta) / DELTA_DIVISOR
        self.rect.center = x, y
        if self.rect.bottom > self.bounds.bottom:
            self.rect.bottom = self.bounds.bottom
            self._dy = -self._dy
        if self.rect.top < self.bounds.top:
            self.rect.top = self.bounds.top
            self._dy = -self._dy
        if self.rect.right > self.bounds.right:
            self.rect.right = self.bounds.right
            self._dx = -self._dx
        if self.rect.left < self.bounds.left:
            self.rect.left = self.bounds.left
            self._dx = -self._dx


class BoundsSpawner:
    def __init__(self, config, sprite, bounds):
        """Spawn Sprite(x, y)s at random locations on bounds Rect."""
        self.sprite = sprite
        self.bounds = bounds

    def _xy(self):
        while True:
            x = random.randint(self.bounds.left, self.bounds.right)
            y = random.randint(self.bounds.top, self.bounds.bottom)
            match random.randint(0, 3):
                case 0:  # top
                    y = self.bounds.top
                case 1:  # right
                    x = self.bounds.right
                case 2:  # bottom
                    y = self.bounds.bottom
                case 3:  # left
                    x = self.bounds.left
            yield x, y

    def spawn(self, count=5):
        for _ in range(count):
            yield self.sprite(*next(self._xy()))


class BufferBoundsSpawner(BoundsSpawner):
    def __init__(self, config, baddie, bounds, buffer=100):
        """Spawn Baddie()s at random locations within inside buffer of bounds Rect."""
        super().__init__(config, baddie, bounds)
        self.buffer = buffer * config.scale_factor

    def _xy(self):
        while True:
            lr = random.randint(self.bounds.left, self.bounds.right)
            tp = random.randint(self.bounds.top, self.bounds.bottom)
            buffer = random.randint(0, self.buffer)
            match random.randint(0, 3):
                case 0:  # top
                    x = lr
                    y = self.bounds.top + buffer
                case 1:  # right
                    x = self.bounds.right - buffer
                    y = tp
                case 2:  # bottom
                    x = lr
                    y = self.bounds.bottom - buffer
                case 3:  # left
                    x = self.bounds.left + buffer
                    y = tp
            yield x, y


class TimedSpawn:
    def __init__(self, spawner, every_ms, imediate=True, cycle=0):
        """Spawn at timed intervals.

        @param spawner: function that returns an iterable of sprites to spawn.
        @param every_ms: milliseconds between spawns.
        @param imediate: spawn first group immediately.
        @param cycle: number of times to spawn, 0 is infinite.
        """
        self.spawner = spawner
        self.every_ms = every_ms
        self.timer = 0 if imediate else every_ms

    def update(self, timedelta):
        """Iterable of the spawned."""
        self.timer -= timedelta
        if self.timer < 0:
            self.timer += self.every_ms
            yield from self.spawner()


class CenteredBackgroundSprite(pygame.sprite.Sprite):
    def __init__(self, bounds, image):
        super().__init__()
        self.image = image
        self.rect = self.image.get_rect()
        self.rect.center = bounds.center


class BaseScreen:
    def __init__(self, config):
        self.sprites = pygame.sprite.Group()

    def event(self, event):
        pass

    def update(self, timedelta):
        self.sprites.update(timedelta)

    def draw(self, display):
        self.sprites.draw(display)


class TitleScreen(BaseScreen):
    FADE_OUT = 500  # milliseconds

    def __init__(self, config):
        super().__init__(config)
        pygame.mixer.music.load(ASSETS_PATH / 'music' / 'title_song.mp3')
        background = load_image('titlescreen.jpg', scaled=False)
        background = pygame.transform.scale_by(background, config.height/background.get_height())
        self.sprites.add(CenteredBackgroundSprite(config.display_rect, background))
        self.sprites.add(CenteredBackgroundSprite(config.display_rect, make_menu((('Start', 's'), ('Quit PPoD', 'q'), ('High Scores', 'h')), 160, 100, bg=(0, 0, 0, 0))))
        self.black = pygame.Surface(config.resolution, flags=pygame.SRCALPHA)
        self.black.fill((0, 0, 0, 0))
        self._fade_out = False

    def event(self, event):
        match event:
            case pygame.event.Event(type=pygame.KEYDOWN, key=pygame.K_s):
                pygame.mixer.music.fadeout(self.FADE_OUT)
                pygame.time.set_timer(constants.STARTPLAY, self.FADE_OUT, 1)
                self._fade_out = 1
            case pygame.event.Event(type=pygame.KEYDOWN, key=pygame.K_q):
                pygame.mixer.music.fadeout(self.FADE_OUT)
                pygame.time.set_timer(pygame.QUIT, self.FADE_OUT, 1)
                self._fade_out = 1

    def update(self, timedelta):
        if self._fade_out:
            self._fade_out += timedelta
            self.black.fill((0, 0, 0, min(255, int(255 * (self._fade_out / self.FADE_OUT)))))
            return
        if not pygame.mixer.music.get_busy():
            pygame.mixer.music.play(-1)
        super().update(timedelta)

    def draw(self, display):
        display.fill((0, 0, 0))
        super().draw(display)
        if self._fade_out:
            display.blit(self.black, (0, 0))
            return


class PauseScreen(BaseScreen):
    def __init__(self, config):
        super().__init__(config)
        self.config = config
        self.sprites.add(CenteredBackgroundSprite(config.display_rect, make_menu((('Resume', 'r'), ('Start Menu', 's'), ('Quit PPoD', 'q')))))

    def event(self, event):
        match event:
            case pygame.event.Event(type=pygame.KEYDOWN, key=pygame.K_ESCAPE):
                return True
            case pygame.event.Event(type=pygame.KEYDOWN, key=pygame.K_r):
                return True
            case pygame.event.Event(type=pygame.KEYDOWN, key=pygame.K_s):
                pygame.event.post(pygame.event.EventType(constants.TITLEMENU))
            case pygame.event.Event(type=pygame.KEYDOWN, key=pygame.K_q):
                pygame.event.post(pygame.event.Event(pygame.QUIT))


class GameplayScreen:
    gameplaysongs = ('bit_banger.mp3', 'chaos_unleashed.mp3', 'pixel_carnage.mp3')

    def __init__(self, config):
        self.config = config
        self.paused = False
        self.pause_screen = PauseScreen(config)
        # Sprite Groups
        self.player = pygame.sprite.Group()
        self.player_projectiles = pygame.sprite.Group()
        self.baddie = pygame.sprite.Group()
        self.explosions = pygame.sprite.Group()

        # Player ship and weapons
        self.ship = PlayerSprite(config)
        self.player.add(self.ship)
        self.ship.addweapon(PewPewCannon(config, self.player_projectiles))
        # self.ship.addweapon(PewPewTurret(config, self.player_projectiles))

        # Baddies
        bawler = BawlerSpawner(config, self.explosions)
        bs = BufferBoundsSpawner(config, bawler, config.display_rect)
        self.wave1 = TimedSpawn(lambda: bs.spawn(random.randint(5, 15)), 3000)

        # Sounds
        pygame.mixer.music.set_endevent(constants.MUSICSTOP)
        pygame.mixer.music.load(ASSETS_PATH / 'music' / random.choice(self.gameplaysongs))

    def event(self, event):
        if self.paused:
            if self.pause_screen.event(event):
                self.paused = False
                pygame.mixer.music.set_volume(self.config.music)
            return
        match event:
            case pygame.event.Event(type=pygame.KEYDOWN, key=pygame.K_SPACE):
                for x in self.baddie:
                    x.take_damage('nuke', 100)
            case pygame.event.Event(type=pygame.KEYDOWN, key=pygame.K_ESCAPE):
                self.paused = True
                self._music_volume = pygame.mixer.music.get_volume()
                pygame.mixer.music.set_volume(self._music_volume / 2)
            case pygame.event.Event(type=constants.MUSICSTOP):
                pygame.mixer.music.load(ASSETS_PATH / 'music' / random.choice(self.gameplaysongs))
                pygame.mixer.music.play(1, fade_ms=100)

    def update(self, timedelta):
        if self.paused:
            self.pause_screen.update(timedelta)
            return

        if not pygame.mixer.music.get_busy():
            pygame.mixer.music.play(1, fade_ms=100)

        # Spawn more baddies
        if baddies := self.wave1.update(timedelta):
            self.baddie.add(*baddies)

        # Update all sprites
        self.explosions.update(timedelta)
        self.player.update(timedelta, self.baddie.sprites())
        self.player_projectiles.update(timedelta)
        self.baddie.update(timedelta, self.ship)

        # Player projectiles impact with baddies
        for baddie, projectiles in pygame.sprite.groupcollide(self.baddie, self.player_projectiles, False, False).items():
            for projectile in projectiles:
                projectile.impact(baddie)
        # Baddies impact with player
        for baddie in pygame.sprite.spritecollide(self.ship, self.baddie, False):
            baddie.impact(self.ship)

    def draw(self, display):
        display.fill((0, 0, 0))
        self.baddie.draw(display)
        self.player_projectiles.draw(display)
        self.player.draw(display)
        self.explosions.draw(display)
        if self.paused:
            self.pause_display.draw(display)


class Game:
    def __init__(self, config):
        log.info('PPoD Start %s', datetime.datetime.utc_now().strftime('%Y-%m-%d %H:%M:%S'))
        self.config = config
        self._debug_font = pygame.font.Font(None, 16 * config.scale_factor)

        # make it global
        global load_image, load_sheet, make_menu  # noqa: PLW0603
        load_image = self.load_image
        load_sheet = self.load_sheet
        make_menu = self.make_menu

        pygame.display.set_caption('Pew Pew or Die')
        display_flags = pygame.SHOWN
        display_size = (config.width, config.height)
        if config.fullscreen:
            display_flags |= pygame.FULLSCREEN | pygame.SCALED
        self.display = pygame.display.set_mode(display_size, display_flags, vsync=1)
        config.screen_bounds = self.display.get_rect()
        log.info('Display driver: %s', pygame.display.get_driver())

        self.screen = TitleScreen(config)

    def make_menu(self, entries, w=240, h=180, bg=(0, 0, 0, 200), fg=(196, 129, 0)):
        scale = self.config.scale_factor
        menu = pygame.Surface((w * scale, h * scale)).convert_alpha()
        menu.fill(bg)
        LEFT = w // 10 * scale
        TOP = h // 10 * scale
        SPACER = (h - 10) // len(entries) * scale
        font = pygame.font.Font(ASSETS_PATH / 'PixelifySans-Regular.ttf', 18 * scale)
        y = TOP
        for entry, _ in entries:
            menu.blit(font.render(entry, False, fg), (LEFT, y))
            y += SPACER
        return menu

    def load_image(self, name, scaled=True):
        """Load, scaled and converted an Source from named image file."""
        fullname = ASSETS_PATH / name
        try:
            image = pygame.image.load(fullname)
            if image.get_alpha():
                image = image.convert_alpha()
            else:
                image = image.convert()
            if scaled:
                image = pygame.transform.scale_by(image, self.config.scale_factor)
        except pygame.error as ex:
            log.exception(f'Cannot load image "{name}" from {fullname}')
            print(f'Cannot load image "{name}" from {fullname}')
            raise SystemExit(ex) from None
        return image

    def load_sheet(self, name, w, h):
        """Return a list of (w, h) Sources from a left to right horizontal sprite sheet."""
        w *= self.config.scale_factor
        h *= self.config.scale_factor
        sheet = self.load_image(name)
        flags = 0
        if sheet.get_alpha():
            flags |= pygame.SRCALPHA
        images = []
        for x in range(0, sheet.get_width(), w):
            image = pygame.Surface((w, h), flags=flags)
            image.blit(sheet, (0, 0), area=(x, 0, w, h))
            images.append(image)
        return images

    def debug_draw(self, display, debug_list):
        fg = (255, 255, 255)
        bg = None
        for x in debug_list:
            text = self._debug_font.render(x, False, fg, bg)
            rect = text.get_rect()
            display.blit(text, rect)

    def run(self):
        pg_clock = pygame.time.Clock()
        exit_to_desktop = False
        while not exit_to_desktop:
            timedelta = pg_clock.tick(60)
            for event in pygame.event.get():
                match event:
                    # Quit
                    case pygame.event.Event(type=pygame.QUIT):
                        exit_to_desktop = True
                        break
                    case pygame.event.Event(type=constants.STARTPLAY):
                        self.screen = GameplayScreen(self.config)
                    case pygame.event.Event(type=constants.TITLEMENU):
                        self.screen = TitleScreen(self.config)
                    case pygame.event.Event(type=constants.DEAD):
                        self.screen = TitleScreen(self.config)
                    case _:
                        self.screen.event(event)
            if not pygame.key.get_focused():
                continue
            self.screen.update(timedelta)
            self.screen.draw(self.display)
            self.debug_draw(self.display, [f'FPS: {pg_clock.get_fps():.2f}'])
            pygame.display.update()
            if next(DEBUG_CYCLE):
                pass

        # All checkes made, clean up and exit.
        pygame.quit()
        log.info('PPoD End %s', datetime.datetime.utc_now().strftime('%Y-%m-%d %H:%M:%S'))
        sys.exit()


if __name__ == '__main__':
    pygame.init()
    config = Config()
    if '-v' in sys.argv:
        logging.basicConfig(level=logging.DEBUG)
    if '-vv' in sys.argv:
        logging.basicConfig(level=logging.DEBUG)
        log.setLevel(logging.DEBUG)
    if '-f' in sys.argv:
        config.fullscreen = True
    for x in sys.argv:
        if x.startswith('-r'):
            config.resolution = int(x[2:])
    ppod = Game(config)
    ppod.run()
