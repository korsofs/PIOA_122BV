@echo off
setlocal enabledelayedexpansion

set branches[0]=feature/changes
set branches[1]=feature/conflict
set branches[2]=task2
set branches[3]=task3
set branches[4]=task4
set branches[5]=task5
set branches[6]=task6

set folders[0]=feature_changes
set folders[1]=feature_conflict
set folders[2]=task2
set folders[3]=task3
set folders[4]=task4
set folders[5]=task5
set folders[6]=task6

for /l %%i in (0,1,6) do (
    echo Processing !branches[%%i]! -^> !folders[%%i]!
    
    git checkout -b temp_!folders[%%i]! origin/!branches[%%i]!
    if not exist !folders[%%i]! mkdir !folders[%%i]!
    
    for /f "delims=" %%f in ('git ls-files') do (
        if not exist !folders[%%i]!\%%~pf mkdir !folders[%%i]!\%%~pf 2>nul
        git mv %%f !folders[%%i]!\%%f 2>nul
    )
    
    git commit -m "Move !branches[%%i]! to !folders[%%i]!"
    git checkout LR1
    
    rem Пытаемся сделать merge, если конфликт - разрешаем в пользу временной ветки
    git merge temp_!folders[%%i]! --allow-unrelated-histories --no-ff -m "Merge !branches[%%i]! as !folders[%%i]!" 2>nul
    if errorlevel 1 (
        echo CONFLICT detected for !branches[%%i]!, resolving automatically...
        
        rem Берём все файлы из временной ветки
        git checkout --theirs .
        git add .
        
        rem Завершаем merge
        git commit -m "Merge !branches[%%i]! as !folders[%%i]! (resolved conflicts)"
    )
    
    rem Принудительно удаляем временную ветку
    git branch -D temp_!folders[%%i]! 2>nul
)

echo Done!
echo.
echo Pushing to remote...
git push origin LR1 --force

echo.
echo All done! Check the result with: git ls-tree -r LR1 --name-only