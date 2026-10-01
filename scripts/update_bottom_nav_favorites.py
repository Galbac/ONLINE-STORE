code = """\"use client\";

import { useEffect, useState } from \"react\";
import Link from \"next/link\";
import { usePathname } from \"next/navigation\";
import { Heart, Home, LayoutGrid, ShoppingBag, User } from \"lucide-react\";

import { cartApi } from \"@/entities/cart\";
import { useFavoritesStore } from \"@/entities/favorite\";
import { cn, ROUTES } from \"@/shared/config\";
import { isAccessTokenValid } from \"@/shared/lib/auth-token\";
import { CART_CHANGED_EVENT, type CartChangedDetail } from \"@/shared/lib/cart-events\";
import {
  FAVORITES_CHANGED_EVENT,
  type FavoritesChangedDetail,
} from \"@/shared/lib/favorite-events\";
import { getStoredAccessToken } from \"@/shared/ui\";

export const BottomNav = () => {
  const pathname = usePathname();
  const [cartCount, setCartCount] = useState<number>(0);
  const [isAuth, setIsAuth] = useState<boolean>(false);
  const favoritesCount = useFavoritesStore((state) => state.items.length);

  useEffect(() => {
    const updateAuth = () => {
      const token = getStoredAccessToken();
      setIsAuth(Boolean(token && isAccessTokenValid(token)));
    };

    updateAuth();

    const fetchCartCount = async () => {
      try {
        const token = getStoredAccessToken();
        if (token && isAccessTokenValid(token)) {
          const summary = await cartApi.getSummary();
          setCartCount(summary.items_count);
        } else {
          setCartCount(0);
        }
      } catch {
        setCartCount(0);
      }
    };

    const fetchFavoritesCount = async () => {
      try {
        const token = getStoredAccessToken();
        if (token && isAccessTokenValid(token)) {
          await useFavoritesStore.getState().fetchFavorites();
        }
      } catch {
        // ignore
      }
    };

    fetchCartCount();
    fetchFavoritesCount();

    const handleCartChanged = (event: Event) => {
      const customEvent = event as CustomEvent<CartChangedDetail>;
      if (typeof customEvent.detail?.itemsCount === "number") {
        setCartCount(customEvent.detail.itemsCount);
      } else {
        void fetchCartCount();
      }
    };

    const handleFavoritesChanged = (event: Event) => {
      const customEvent = event as CustomEvent<FavoritesChangedDetail>;
      if (typeof customEvent.detail?.itemsCount === \"number\") {
        // Handled reactively by store
      } else {
        void fetchFavoritesCount();
      }
      updateAuth();
    };

    window.addEventListener(CART_CHANGED_EVENT, handleCartChanged);
    window.addEventListener(FAVORITES_CHANGED_EVENT, handleFavoritesChanged);

    return () => {
      window.removeEventListener(CART_CHANGED_EVENT, handleCartChanged);
      window.removeEventListener(FAVORITES_CHANGED_EVENT, handleFavoritesChanged);
    };
  }, [pathname]);

  if (pathname.startsWith(\"/admin\")) {
    return null;
  }

  const isFavoritesActive =
    pathname === ROUTES.PROFILE_FAVORITES ||
    pathname === \"/favorites\" ||
    pathname.startsWith(\"/profile/favorites\");

  const isProfileActive =
    (pathname.startsWith(\"/profile\") && !isFavoritesActive) || pathname === ROUTES.LOGIN;

  const items = [
    {
      href: ROUTES.HOME,
      label: \"Главная\",
      icon: Home,
      isActive: pathname === ROUTES.HOME,
    },
    {
      href: ROUTES.CATALOG,
      label: \"Каталог\",
      icon: LayoutGrid,
      isActive: pathname.startsWith(\"/catalog\") || pathname.startsWith(\"/category\"),
    },
    {
      href: ROUTES.CART,
      label: \"Корзина\",
      icon: ShoppingBag,
      badge: cartCount > 0 ? (cartCount > 99 ? \"99+\" : String(cartCount)) : null,
      badgeClassName: \"bg-emerald-600 text-white\",
      isActive: pathname === ROUTES.CART,
    },
    {
      href: ROUTES.PROFILE_FAVORITES,
      label: \"Избранное\",
      icon: Heart,
      badge: favoritesCount > 0 ? (favoritesCount > 99 ? \"99+\" : String(favoritesCount)) : null,
      badgeClassName: \"bg-rose-500 text-white\",
      isActive: isFavoritesActive,
    },
    {
      href: isAuth ? ROUTES.PROFILE : ROUTES.LOGIN,
      label: isAuth ? \"Профиль\" : \"Войти\",
      icon: User,
      isActive: isProfileActive,
    },
  ];

  return (
    <nav
      aria-label=\"Мобильная навигация\"
      className=\"border-border/80 bg-bg-primary/95 supports-[backdrop-filter]:bg-bg-primary/80 fixed right-0 bottom-0 left-0 z-50 border-t backdrop-blur-md transition-all lg:hidden\"
      style={{ paddingBottom: \"max(var(--sab, 0px), 8px)\" }}
    >
      <div className=\"grid grid-cols-5 items-center justify-around px-2 pt-2\">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <Link
              key={item.label}
              href={item.href}
              onClick={() => {
                if (typeof window !== \"undefined\" && \"vibrate\" in navigator) {
                  try {
                    navigator.vibrate(12);
                  } catch (_) {}
                }
              }}
              className={`relative flex flex-col items-center justify-center py-1 text-center transition active:scale-95 min-w-0 ${
                item.isActive
                  ? \"text-emerald-600 font-bold\"
                  : \"text-slate-500 hover:text-slate-800 font-medium\"
              }`}
            >
              <div className=\"relative\">
                <Icon
                  size={20}
                  className={`sm:w-[22px] sm:h-[22px] ${
                    item.isActive ? \"stroke-[2.4]\" : \"stroke-[1.8]\"
                  }`}
                />
                {item.badge ? (
                  <span
                    className={cn(
                      \"absolute -top-1.5 -right-2.5 flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[9px] font-bold shadow-xs\",
                      item.badgeClassName ?? \"bg-emerald-600 text-white\",
                    )}
                  >
                    {item.badge}
                  </span>
                ) : null}
              </div>
              <span className=\"mt-1 text-[10px] sm:text-[11px] leading-tight tracking-tight truncate max-w-full px-0.5\">
                {item.label}
              </span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
};
\"\"\"

path = \"/Users/zidansaparbegov/PycharmProjects/GroceryStore-front/src/widgets/bottom-nav/ui/BottomNav.tsx\"
with open(path, \"w\", encoding=\"utf-8\") as f:
    f.write(code)

print(\"BottomNav.tsx updated successfully with favorites badge!\")
