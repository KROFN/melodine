#!/usr/bin/env python3

import sys

def main():
    try:
        from melodine.app import MelodineApp
        app = MelodineApp()
        app.run()
    except KeyboardInterrupt:
        print("\n👋 До встречи!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()