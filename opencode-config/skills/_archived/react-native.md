# Skill: React Native
# Loaded on-demand when working with React Native, Expo, mobile apps

## Expo vs Bare Workflow

- **Expo (managed)**: Use for most projects. EAS Build handles native compilation. `npx create-expo-app`.
- **Bare workflow**: Eject only when you need custom native modules not supported by Expo.
- **Expo Modules API**: Write custom native modules without leaving managed workflow.

```tsx
// app.json — Expo config
{
  "expo": {
    "plugins": ["expo-camera", ["expo-image-picker", { "photosLibraryPermission": "Allow access" }]]
  }
}
```

## Navigation (React Navigation)

```tsx
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';

// Type-safe navigation
type RootStackParamList = {
  Home: undefined;
  Profile: { userId: string };
};

const Stack = createNativeStackNavigator<RootStackParamList>();
const Tab = createBottomTabNavigator();

function App() {
  return (
    <NavigationContainer>
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        <Stack.Screen name="Home" component={HomeScreen} />
        <Stack.Screen name="Profile" component={ProfileScreen} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}

// Deep linking config
const linking = {
  prefixes: ['myapp://', 'https://myapp.com'],
  config: { screens: { Home: '', Profile: 'user/:userId' } },
};
```

## Styling & Responsive Design

```tsx
import { StyleSheet, Platform, Dimensions } from 'react-native';

const { width } = Dimensions.get('window');
const isTablet = width >= 768;

const styles = StyleSheet.create({
  container: {
    flex: 1,
    paddingTop: Platform.OS === 'ios' ? 44 : 0,
    flexDirection: isTablet ? 'row' : 'column',
  },
});

// Platform-specific files: Button.ios.tsx / Button.android.tsx
// RN auto-resolves the correct file per platform.
```

## Performance: FlatList & Memoization

```tsx
import { FlatList, memo } from 'react';

const Item = memo(({ title }: { title: string }) => <Text>{title}</Text>);

<FlatList
  data={items}
  keyExtractor={(item) => item.id}
  renderItem={({ item }) => <Item title={item.title} />}
  getItemLayout={(_, index) => ({ length: 60, offset: 60 * index, index })}
  windowSize={5}
  maxToRenderPerBatch={10}
  removeClippedSubviews={true}
/>
```

## Animations (Reanimated + Gesture Handler)

```tsx
import Animated, { useSharedValue, useAnimatedStyle, withSpring } from 'react-native-reanimated';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';

function SwipeCard() {
  const translateX = useSharedValue(0);
  const gesture = Gesture.Pan()
    .onUpdate((e) => { translateX.value = e.translationX; })
    .onEnd(() => { translateX.value = withSpring(0); });

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: translateX.value }],
  }));

  return (
    <GestureDetector gesture={gesture}>
      <Animated.View style={animatedStyle}><Text>Swipe me</Text></Animated.View>
    </GestureDetector>
  );
}
```

## Storage & Push Notifications

```tsx
// MMKV — fast synchronous storage (prefer over AsyncStorage)
import { MMKV } from 'react-native-mmkv';
const storage = new MMKV();
storage.set('user.token', 'abc123');
const token = storage.getString('user.token');

// Push notifications (Expo)
import * as Notifications from 'expo-notifications';
const { status } = await Notifications.requestPermissionsAsync();
const pushToken = (await Notifications.getExpoPushTokenAsync()).data;
```

## Testing

```tsx
import { render, fireEvent } from '@testing-library/react-native';

test('button triggers action', () => {
  const onPress = jest.fn();
  const { getByText } = render(<Button title="Submit" onPress={onPress} />);
  fireEvent.press(getByText('Submit'));
  expect(onPress).toHaveBeenCalledTimes(1);
});
```

## EAS Build & OTA Updates

```bash
# Build for production
eas build --platform all --profile production
# Submit to stores
eas submit --platform ios
# OTA update (no store review)
eas update --branch production --message "Fix crash on login"
```

## Best Practices

- Enable **Hermes** engine (default in Expo SDK 49+) for faster startup and lower memory.
- Use `React.memo`, `useMemo`, `useCallback` to prevent unnecessary re-renders.
- Avoid inline styles in lists — use `StyleSheet.create` for caching.
- Test on real devices — simulators hide performance issues.
- Use `expo-updates` for OTA; gate breaking changes behind feature flags.
